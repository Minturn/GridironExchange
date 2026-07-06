# Hosting runbook

Two phases (SPEC §9): demo from the Mac now, Fly.io for the season.

## Phase A — friends demo from this Mac (Tailscale Funnel, free)

1. Install Tailscale (`brew install --cask tailscale`), sign in, and in the
   admin console enable **HTTPS certificates** + **Funnel** for your tailnet
   (Settings → Feature previews / Access controls — one-time).
2. Start the app (one process serves API + UI):
   ```bash
   cd ~/GridironExchange/frontend && npm run build
   cd ~/GridironExchange/backend
   source .venv/bin/activate
   alembic upgrade head && python scripts/seed_demo.py   # first time only
   GRIDX_SECRET_KEY="$(openssl rand -hex 32)" uvicorn app.main:app --port 8200
   ```
3. Expose it: `tailscale funnel 8200` → gives a stable
   `https://<your-mac>.<tailnet>.ts.net` URL anyone can open.
4. Keep the Mac awake during demo windows: `caffeinate -dims` in another tab.
5. Friends: open the URL → **Join with an invite code** → code `demo`
   (or the seeded logins ryan/sal/derek/matty, password `demo123`).

Stop sharing: `tailscale funnel reset`. A sleeping laptop kills the demo —
fine for showings, not for the season.

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
