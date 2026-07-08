# Hosting on a Synology NAS (DS220+)

The DS220+ is Intel-based and runs **Container Manager** (Docker), so it can host the app
in a container. The win over the Mac: the NAS is **always on**, so the app and the public
link stay up 24/7 — no more "Mac went to sleep." It's also free (your hardware) and keeps
the data at home. This is the recommended host for the friend-league season.

> Everything here is done once. After it's running, updates are one rebuild.

## What you'll end up with
- The app running as a container on the NAS, database on a NAS folder (survives reboots).
- The season scheduler ON (Tuesday dividends, nightly sync, game locks run themselves).
- A public `https://…ts.net` link via Tailscale running on the NAS.

---

## 1. One-time NAS prep
1. **Install Container Manager**: DSM → **Package Center** → search **Container Manager** → Install.
2. **Enable SSH** (needed for a couple of commands): DSM → **Control Panel → Terminal & SNMP** →
   check **Enable SSH service** → Apply.
3. Pick a folder for the project, e.g. create a shared folder `docker`, so the path is
   `/volume1/docker/gridiron`.

## 2. Get the code onto the NAS
SSH into the NAS (`ssh ryan@<nas-ip>`), then clone the repo. It's private, so use a GitHub
**Personal Access Token** (github.com → Settings → Developer settings → Tokens → generate one
with `repo` scope):

```
cd /volume1/docker
git clone https://<YOUR_TOKEN>@github.com/Minturn/GridironExchange.git gridiron
```

(No git on the NAS? Install **Git Server** from Package Center, or copy the folder over with
File Station — but exclude `node_modules`, `.venv`, and `dist`, which are huge and rebuilt anyway.)

## 3. Bring your league + login secret over (so nothing resets)
On the **Mac**, find your session secret:

```
grep GRIDX_SECRET_KEY ~/GridironExchange/backend/.env
```

Create the NAS env file with that exact value so everyone stays logged in:

```
cd /volume1/docker/gridiron
mkdir -p data
printf 'GRIDX_SECRET_KEY=%s\n' 'PASTE_THE_KEY_FROM_THE_MAC' > .env
```

Then copy the current league database from the Mac to the NAS's `data` folder (so thezipr23,
Jeff, all trades come with you). Easiest: File Station → upload
`~/GridironExchange/backend/gridx.db` into `/volume1/docker/gridiron/data/`. Or from the Mac:

```
scp ~/GridironExchange/backend/gridx.db ryan@<nas-ip>:/volume1/docker/gridiron/data/gridx.db
```

(Skip the copy for a fresh start — the container creates an empty DB and the first person to
register becomes commissioner.)

## 4. Build + run it (Container Manager)
1. Open **Container Manager → Project → Create**.
2. **Path**: `/volume1/docker/gridiron` · **Source**: it'll detect `docker-compose.yml`.
3. Click **Build** / **Next** → **Done**. First build takes a few minutes (it builds the web
   UI, then the server). Watch the log; when it shows `Uvicorn running on … :8200`, it's up.
4. Test on your network: open `http://<nas-ip>:8200` — you should see the sign-in screen.

## 5. Make it public (Tailscale on the NAS)
1. **Package Center** → search **Tailscale** → Install → open it → **Log in** (same Tailscale
   account). The NAS joins your tailnet as a new machine (e.g. `synology`).
2. SSH into the NAS and turn on the funnel (HTTPS is already enabled on your tailnet):

```
sudo /var/packages/Tailscale/target/bin/tailscale funnel --bg 8200
```

3. Get the public URL:

```
sudo /var/packages/Tailscale/target/bin/tailscale funnel status
```

It prints a new link like `https://synology.tail3c5b35.ts.net`. **That's the season URL** —
share it + the invite code `kickoff` with your friends. (It's a different URL than the Mac's
because it's a different machine. You can retire the Mac funnel with `tailscale funnel reset`
on the Mac.)

## 6. Updating later
When I ship changes, on the NAS:

```
cd /volume1/docker/gridiron && git pull
```

then **Container Manager → your Project → Build** again (or Stop/Start). The `data` folder
(your league) is untouched; migrations apply automatically on start.

---

## Troubleshooting
- **Build runs out of memory** (DS220+ has 2 GB): add a swap file, or bump the NAS to 6 GB
  RAM (cheap SODIMM). If it still struggles, tell me — I'll set up a GitHub Action that builds
  the image in the cloud and publishes it, so the NAS just *pulls* a finished image (no build).
- **Public link 502**: the container isn't running — check Container Manager → Project is
  "Running", and `http://<nas-ip>:8200` works on the LAN first.
- **Tailscale funnel command not found**: the binary is under
  `/var/packages/Tailscale/target/bin/tailscale`; use the full path (as above).
- **Everyone got logged out after the move**: the NAS `.env` `GRIDX_SECRET_KEY` didn't match
  the Mac's. Fix the value in `.env`, rebuild — or just have people sign in again once.

## When it becomes a product
For public/multi-league, move to **Fly.io** (`docs/hosting.md`, Phase B) — off your home
network and internet, and it scales. The NAS is ideal for one friend league; Fly.io for many.
