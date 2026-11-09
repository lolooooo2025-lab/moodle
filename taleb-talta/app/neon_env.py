"""Neon `.env.local` support.

The Neon CLI (`neon init` / `neon deploy` / `neon env pull`) writes branch
connection details into `.env` and `.env.local` at the project root. This module
loads those files into the process environment and maps Neon's Postgres keys
onto the app's own settings.

Key contract (taken from the Neon CLI's `NEON_ENV_VAR_KEYS`):

    DATABASE_URL            pooled endpoint (pgbouncer)
    DATABASE_URL_UNPOOLED   direct endpoint  <- the one asyncpg needs
    NEON_AUTH_BASE_URL / NEON_AUTH_JWKS_URL
    NEON_DATA_API_URL
    NEON_REALTIME_URL / NEON_REALTIME_SECRET
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_ENDPOINT_URL_S3 / AWS_REGION
    NEON_BRANCH / NEON_BRANCH_ID

Rules:

* Real environment variables always win (Render, systemd, CI).
* `.env.local` overrides `.env`, matching the Neon CLI's own precedence.
* Only missing keys are filled in; nothing already set is overwritten.
* `TT_DATABASE_URL` prefers `DATABASE_URL_UNPOOLED`: asyncpg uses prepared
  statements, which break behind Neon's pooled (pgbouncer) endpoint.
* Values are never logged, printed, or returned — only key names.

Both env files are git-ignored (`.env`, `.env.*`) and must never be committed
or placed in a web-served directory.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ENV_FILE_NAMES = (".env", ".env.local")

# libpq/Neon options that are not valid asyncpg.connect() keyword arguments.
# channel_binding is advertised by Neon but unsupported by asyncpg; dropping it
# is safe on the direct endpoint. The pooled endpoint needs options=endpoint,
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
                f"unsupported database URL option: {key}; use the Neon direct "
                "connection string (DATABASE_URL_UNPOOLED)"
            )
        query.append((key, value))

    if sslmode is not None:
        if sslmode not in SSLMODES:
            raise ValueError("invalid sslmode in TT_DATABASE_URL")
        if not any(key == "ssl" for key, _ in query):
            query.append(("ssl", sslmode))

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file. Never logs values; tolerates quotes and `export`."""
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = raw.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        values[key] = value
    return values


def load_neon_env(root: Path | str | None = None,
                  environ: dict[str, str] | None = None) -> list[str]:
    """Load `.env` / `.env.local` and map Neon's Postgres URL onto TT_DATABASE_URL.

    Returns the sorted list of key names that were added (never their values).
    """
    env = os.environ if environ is None else environ
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent

    merged: dict[str, str] = {}
    for name in ENV_FILE_NAMES:
        merged.update(parse_env_file(base / name))
    override = env.get("TT_NEON_ENV_FILE")
    if override:
        merged.update(parse_env_file(Path(override)))

    added: list[str] = []
    for key, value in merged.items():
        if value and not env.get(key):
            env[key] = value
            added.append(key)

    if not env.get("TT_DATABASE_URL"):
        # Direct endpoint first: asyncpg prepared statements break on pgbouncer.
        raw = env.get("DATABASE_URL_UNPOOLED") or env.get("DATABASE_URL") or ""
        if raw:
            try:
                env["TT_DATABASE_URL"] = normalize_database_url(raw)
            except ValueError as exc:
                raise ValueError(
                    f"{exc}. Set TT_DATABASE_URL to the Neon direct URL, or make "
                    "sure DATABASE_URL_UNPOOLED is present in .env.local"
                ) from None
            added.append("TT_DATABASE_URL")

    return sorted(added)
