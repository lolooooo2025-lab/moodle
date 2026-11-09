"""Render free-demo launcher.

Normalizes a Neon direct PostgreSQL URL for SQLAlchemy asyncpg, applies safe
free-tier defaults, and execs Uvicorn on Render's PORT. Never prints secrets.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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

# These libpq/Neon options are not valid asyncpg.connect() keyword arguments.
# channel_binding is advertised by Neon but unsupported by asyncpg; dropping it
# is safe for the direct endpoint. The pooled endpoint needs options=endpoint,
# so we fail closed on that rather than silently breaking pooled connections.
DROPPED_QUERY = {"channel_binding"}
UNSUPPORTED_QUERY = {
    "options", "sslcert", "sslkey", "sslrootcert",
    "sslcrl", "sslpassword", "sslnegotiation",
}
SSLMODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def normalize_database_url(raw: str) -> str:
    """Convert a Neon/libpq URL to the form expected by SQLAlchemy asyncpg."""
    raw = raw.strip()
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://"):
        raw = "postgresql+asyncpg://" + raw[len("postgresql://"):]
    if not raw.startswith("postgresql+asyncpg://"):
        raise ValueError("TT_DATABASE_URL must be a PostgreSQL URL")

    parts = urlsplit(raw)
    if not parts.hostname or not parts.path or parts.path == "/":
        raise ValueError("TT_DATABASE_URL must include host and database name")

    query: list[tuple[str, str]] = []
    sslmode = None
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            sslmode = value
            continue
        if key in DROPPED_QUERY:
            continue
        if key in UNSUPPORTED_QUERY:
            raise ValueError(
                f"unsupported database URL option: {key}; use the Neon direct connection string"
            )
        query.append((key, value))

    if sslmode is not None:
        if sslmode not in SSLMODES:
            raise ValueError("invalid sslmode in TT_DATABASE_URL")
        if not any(key == "ssl" for key, _ in query):
            query.append(("ssl", sslmode))

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def main() -> int:
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
