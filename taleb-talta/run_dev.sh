#!/usr/bin/env bash
# Dev server: real PostgreSQL (pgserver) + uvicorn on 0.0.0.0:8000.
set -e
cd "$(dirname "$0")"
export TT_PGDATA="${TT_PGDATA:-/home/user/tt_pgdata}"
export PYTHONPATH="$(pwd)"
export TT_DATABASE_URL="$(/home/user/ttvenv/bin/python tools/devdb.py url 2>/dev/null | tail -1)"
export TT_DEBUG=1
export TT_ALLOW_FRAMING=1   # live preview embeds the app in a cross-site iframe
exec /home/user/ttvenv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
