#!/bin/bash
# Gridiron Exchange — one-tap demo launcher (hosting Phase A).
# Double-click this file in Finder, OR run:  bash "Run Demo.command"
# It builds the UI, prepares the database, keeps the Mac awake, and serves the
# whole app (API + UI) on http://127.0.0.1:8200. Leave the window open; Ctrl-C stops.
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

PY=/opt/homebrew/bin/python3.13   # system python3 is too old (3.9)

echo "▶  Building the front end…"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then npm install --no-fund --no-audit; fi
npm run build

echo "▶  Preparing the back end…"
cd "$ROOT/backend"
if [ ! -d .venv ]; then "$PY" -m venv .venv && .venv/bin/pip install -q -r requirements.txt; fi

# Persistent session secret → nobody gets logged out when you restart the app.
if [ ! -f .env ]; then
  echo "GRIDX_SECRET_KEY=$(openssl rand -hex 32)" > .env
  echo "   created backend/.env (session secret)"
fi

# Idempotent: creates gridx.db on first run, no-ops afterward.
.venv/bin/alembic upgrade head
.venv/bin/python scripts/seed_demo.py

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  Gridiron Exchange is live at  http://127.0.0.1:8200"
echo "  Demo logins: ryan / sal / derek / matty   password: demo123"
echo "  Invite code for new friends: demo"
echo ""
echo "  To share it, open a NEW Terminal tab and run:"
echo "      tailscale funnel 8200"
echo ""
echo "  Leave THIS window open. Press Ctrl-C to stop the exchange."
echo "════════════════════════════════════════════════════════════════"
echo ""

# caffeinate keeps the Mac fully awake for as long as the server runs.
exec caffeinate -dims .venv/bin/uvicorn app.main:app --port 8200
