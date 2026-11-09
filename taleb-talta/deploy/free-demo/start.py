"""Render free-demo launcher.

Normalizes a Neon direct PostgreSQL URL for SQLAlchemy asyncpg, applies safe
free-tier defaults, and execs Uvicorn on Render's PORT. Never prints secrets.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# The launcher runs as a script (python deploy/free-demo/start.py), so the repo
# root is not on sys.path yet. Add it to reuse the app's Neon env loader.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.neon_env import load_neon_env, normalize_database_url  # noqa: E402,F401

REQUIRED = (
    "TT_DATABASE_URL",
    "TT_OWNER_PHONE",
    "TT_OWNER_PASSWORD",
    "TT_VAPID_SUBJECT",
    "TT_PASSWORD_PEPPER",
    "TT_SESSION_SECRET",
    "TT_CRON_TOKEN",
    "TT_STREAM_SECRET",
    "TT_VAPID_PRIVATE_KEY",
)


def main() -> int:
    # Pick up Neon CLI output (.env / .env.local) when running locally.
    # On Render the values come from the dashboard and take precedence.
    try:
        load_neon_env(ROOT)
    except ValueError as exc:
        print(f"free-demo: {exc}", file=sys.stderr)
        return 2

    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print("free-demo: missing environment variables: " + ", ".join(missing), file=sys.stderr)
        return 2

    try:
        database_url = normalize_database_url(os.environ["TT_DATABASE_URL"])
    except ValueError as exc:
        print(f"free-demo: {exc}", file=sys.stderr)
        return 2
    os.environ["TT_DATABASE_URL"] = database_url

    if not os.environ.get("TT_PUBLIC_ORIGIN"):
        os.environ["TT_PUBLIC_ORIGIN"] = os.environ.get("RENDER_EXTERNAL_URL", "")

    # Free-demo safety defaults. This launcher is not used by the VPS path.
    os.environ["TT_DEMO_MODE"] = "1"
    os.environ["TT_COOKIE_SECURE"] = "1"
    os.environ["TT_DEBUG"] = "0"
    os.environ["TT_ALLOW_FRAMING"] = "0"
    os.environ.setdefault("TT_DB_POOL_SIZE", "2")
    os.environ.setdefault("TT_DB_MAX_OVERFLOW", "2")

    port = os.environ.get("PORT", "10000")
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        print("free-demo: PORT must be a valid TCP port", file=sys.stderr)
        return 2

    print(f"free-demo: starting uvicorn on 0.0.0.0:{port} (demo mode)", flush=True)
    os.execvp(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", port,
        "--proxy-headers", "--forwarded-allow-ips", "*",
        "--timeout-graceful-shutdown", "25",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
