# Hosting on a Synology NAS (DS220+)

The DS220+ is Intel-based and runs **Container Manager**, so it can host the app in a
container. The win over the Mac: the NAS is **always on**, so the app and the public link
stay up 24/7 — no more "Mac went to sleep." Free, and the data stays home. This is the
recommended host for the friend-league season.

**Build strategy:** the DS220+ only has 2 GB RAM, so it does **not** build the image.
Instead, **GitHub Actions builds it in the cloud** and publishes it to the GitHub Container
Registry (GHCR); the NAS just **pulls the finished image**. So the NAS only needs the
`docker-compose.yml` file, not the source.

## What you'll end up with
- The app as a container on the NAS, database on a NAS folder (survives reboots/updates).
- The season scheduler ON (Tuesday dividends, nightly sync, game locks run themselves).
- A public `https://…ts.net` link via Tailscale on the NAS.

---

## 1. Publish the image (one push)
On the Mac:

```
cd ~/GridironExchange && git push origin master
```

That push triggers the **Build and publish Docker image** workflow. Watch it at
github.com → your repo → **Actions**; wait for the green check (~2–3 min). It publishes
`ghcr.io/minturn/gridironexchange:latest`.

## 2. NAS prep (one-time)
1. **Container Manager** is installed ✓.
2. **Enable SSH**: DSM → Control Panel → Terminal & SNMP → **Enable SSH service** → Apply.
3. Create a shared folder so you have `/volume1/docker/gridiron`, with a `data` subfolder.

## 3. Put three small things in that folder
The NAS needs only the compose file, a secret, and your league database:

- **`docker-compose.yml`** — copy just this one file from the repo into
  `/volume1/docker/gridiron/` (File Station upload, or paste it in DSM's Text Editor).
- **`.env`** — reuse the Mac's session key so nobody gets logged out. On the Mac:
  ```
  grep GRIDX_SECRET_KEY ~/GridironExchange/backend/.env
  ```
  Then create `/volume1/docker/gridiron/.env` containing that one line
  (`GRIDX_SECRET_KEY=...`).
- **`data/gridx.db`** — bring your league over. From the Mac:
  ```
  scp ~/GridironExchange/backend/gridx.db ryan@<nas-ip>:/volume1/docker/gridiron/data/gridx.db
  ```
  (Skip this for a fresh start — the container makes an empty DB and the first to register
  becomes commissioner.)

## 4. Let the NAS pull a private image
The GHCR image is private, so log the NAS into the registry once:
**Container Manager → Registry → Settings (⚙) → Add** → `ghcr.io` with your **GitHub
username** and a **Personal Access Token** (github.com → Settings → Developer settings →
Tokens → scope `read:packages`).

*(Prefer no token? Make the package public: github.com → your profile → Packages →
gridironexchange → Package settings → Change visibility → Public. Then skip this step.)*

## 5. Run it
1. **Container Manager → Project → Create.**
2. **Path** `/volume1/docker/gridiron` → it detects `docker-compose.yml` (which *pulls* the
   image — no building on the NAS).
3. **Run.** It pulls the image and starts; the log ends with `Uvicorn running on … :8200`.
4. Test on your LAN: open `http://<nas-ip>:8200` — you should see the sign-in screen.

## 6. Make it public (Tailscale on the NAS)
1. **Package Center** → install **Tailscale** → open → **Log in** (same account). The NAS
   joins your tailnet as a new machine.
2. SSH in and turn on the funnel (HTTPS is already enabled on your tailnet):
   ```
   sudo /var/packages/Tailscale/target/bin/tailscale funnel --bg 8200
   ```
3. Get the URL:
   ```
   sudo /var/packages/Tailscale/target/bin/tailscale funnel status
   ```
   It prints a link like `https://synology.tail3c5b35.ts.net` — **that's the season URL.**
   Share it with the invite code `kickoff`. (Retire the Mac's funnel with
   `tailscale funnel reset` on the Mac.)

## 7. Updating later
When I ship changes: push to GitHub → the Action rebuilds the image automatically. On the
NAS, **Container Manager → your Project → pull + restart** (or add **Watchtower** to
auto-pull). Your `data` folder (the league) is untouched; migrations apply on start.

---

## Troubleshooting
- **Action fails**: open the failed run under github.com → Actions for the log.
- **NAS "pull access denied"**: the GHCR login (step 4) didn't take, or the token lacks
  `read:packages`. Re-add the `ghcr.io` registry, or make the package public.
- **Public link 502**: the container isn't running — confirm the Project is "Running" and
  `http://<nas-ip>:8200` works on the LAN first.
- **`tailscale` not found**: use the full path
  `/var/packages/Tailscale/target/bin/tailscale`.
- **Everyone logged out after the move**: the NAS `.env` `GRIDX_SECRET_KEY` didn't match the
  Mac's — fix it and restart, or have people sign in again once.

## When it becomes a product
For public/multi-league, move to **Fly.io** (`docs/hosting.md`, Phase B) — off your home
network, and it scales. The NAS is ideal for one friend league; Fly.io for many.
