# Hosting runbook

Two phases (SPEC §9): demo from the Mac now, Fly.io for the season.

## Phase A — friends demo from this Mac (Tailscale Funnel, free)

Goal: a public `https://…ts.net` link your friends open in any browser, served
straight from this Mac. Two windows total once it's set up — the app, and the
share command. **Do the one-time setup once; after that a demo is: double-click,
run one command, send the link.**

### One-time setup (~10 min, do it once)

**1. Install Tailscale and sign in.**
```bash
brew install --cask tailscale
open -a Tailscale
```
The Tailscale icon appears in the menu bar → click it → **Log in…** → sign in
(Google/GitHub/email). You'll see "Connected" and a machine name like
`ryans-macbook`. That machine name is the start of your public URL.

**2. Put the `tailscale` command on your PATH** (the GUI app hides it inside the
bundle). Run once:
```bash
sudo ln -sf /Applications/Tailscale.app/Contents/MacOS/Tailscale /usr/local/bin/tailscale
tailscale version    # confirms it works
```

**3. Turn on HTTPS for your tailnet** (Funnel needs a real cert). Open the admin
console → **DNS** tab → https://login.tailscale.com/admin/dns →
enable **MagicDNS** (if not already) and click **Enable HTTPS**. One toggle, once.

**4. Allow Funnel.** Run the share command once now to trigger the permission
check:
```bash
tailscale funnel 8200
```
- If it prints a URL, you're done — Ctrl-C and move on.
- If it errors that Funnel isn't permitted, it prints the exact JSON snippet to
  paste. Open the admin console → **Access controls** →
  https://login.tailscale.com/admin/acls → add the printed `nodeAttrs` block
  (it grants the `funnel` attribute to your machines) → **Save** → re-run.

### Every demo (three steps)

**1. Start the app** — double-click **`Run Demo.command`** in the
`GridironExchange` folder (Finder), or in a terminal:
```bash
cd ~/GridironExchange && ./"Run Demo.command"
```
It builds the UI, sets up the database on first run, **keeps the Mac awake**, and
serves everything on `http://127.0.0.1:8200`. Leave this window open. (First run
is slower — it builds the front end and creates the venv.)

> If Finder says it can't run the file: right-click → **Open** → **Open** once to
> clear the macOS quarantine prompt; after that double-click works.

**2. Share it** — open a **new** Terminal tab/window (⌘T) and run:
```bash
tailscale funnel 8200
```
It prints your public link, e.g. `https://ryans-macbook.tail1234.ts.net`. Keep
this window open too. (Prefer fire-and-forget? `tailscale funnel --bg 8200`
backgrounds it; `tailscale funnel status` reprints the URL.)

**3. Send the link.** Text your friends the `https://…ts.net` URL plus:
> Join code: **demo** — pick any name + password on the join screen.

They land on the sign-in screen → **"New here? Join with an invite code"** →
code `demo`. (You can also hand out the seeded logins ryan/sal/derek/matty,
password `demo123`, but a fresh join per person is the better demo.)

### When you're done

- **Stop sharing:** `tailscale funnel reset` (or Ctrl-C the funnel window).
- **Stop the app:** Ctrl-C the `Run Demo.command` window (this also lets the Mac
  sleep again).

### Troubleshooting

| Symptom | Fix |
|---|---|
| Friend sees "This site can't be reached" | The app window isn't running, or the funnel isn't up. Both windows must stay open. Check `tailscale funnel status`. |
| `tailscale: command not found` | Redo one-time step 2 (the PATH symlink). |
| Funnel error about permission / `funnel` attribute | Redo one-time step 4 — paste the printed ACL snippet into Access controls. |
| No HTTPS / cert error | Redo one-time step 3 — Enable HTTPS in the admin DNS tab. |
| `address already in use` on 8200 | An old copy is still running: `lsof -ti tcp:8200 \| xargs kill`, then relaunch. |
| Friends get logged out after you restart | Shouldn't happen — the secret is pinned in `backend/.env`. If you deleted that file, a new one is generated (new secret → everyone re-logs-in once). |
| Link works on your wifi but not their phone | Make sure you used **`funnel`** (public), not `serve` (tailnet-only). `funnel` is the public one. |
| Demo data got messy before a real showing | Reset to the clean seed: stop the app, `rm ~/GridironExchange/backend/gridx.db`, relaunch. |

A sleeping/closed laptop kills the demo — fine for live showings, not for the
season. When friends want to check portfolios all week, move to Phase B.

## Phase B — the season (Fly.io, ~$5–10/mo)

```bash
brew install flyctl && fly auth signup           # or fly auth login
cd ~/GridironExchange
fly launch --no-deploy --copy-config             # accepts fly.toml; pick app name + region sjc
fly postgres create --name gridx-db --region sjc --vm-size shared-cpu-1x --initial-cluster-size 1
fly postgres attach gridx-db                     # PRINTS the connection string — copy it
# The app reads GRIDX_DATABASE_URL and SQLAlchemy needs the postgresql+psycopg2:// scheme,
# so paste the printed URL with the scheme swapped (postgres:// -> postgresql+psycopg2://):
fly secrets set GRIDX_DATABASE_URL='postgresql+psycopg2://<user>:<pw>@gridx-db.flycast:5432/<db>'
fly secrets set GRIDX_SECRET_KEY="$(openssl rand -hex 32)"
fly deploy                                       # builds the Dockerfile remotely (no local Docker needed), runs migrations, boots
fly open                                         # -> https://<app>.fly.dev
```

Notes:
- `GRIDX_ENABLE_SCHEDULER=1` is set in fly.toml — game locks + Tuesday
  dividends run themselves; `auto_stop_machines=false` keeps the scheduler alive.
- Custom domain later: `fly certs add exchange.<yourdomain>.com` + a CNAME.
- Bootstrap the real league: register first (first member in = commissioner),
  Commissioner → Sync players, then Opening Bell with the projections JSON from
  `python scripts/projections_snapshot.py 2026` (run locally against prod by
  setting GRIDX_DATABASE_URL, or paste the JSON into the UI).
- Ongoing deploys are just `fly deploy`. Logs: `fly logs`.

## Season-start checklist (Sep 1 Opening Bell)

1. `fly deploy` latest.
2. Register commissioner account; set league invite code by seeding the league
   row (or use scripts/seed via `fly ssh console`).
3. Commissioner → **Sync players**.
4. `python scripts/projections_snapshot.py 2026` → paste into **Opening Bell**.
5. Send friends the URL + invite code. Trading is live immediately; first
   game locks/dividends happen automatically Week 1.
