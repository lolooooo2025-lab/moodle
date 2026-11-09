#!/usr/bin/env bash
# Create a PostgreSQL custom-format dump outside the web root.
# Usage: sudo bash deploy/backup.sh
set -euo pipefail
source "$(dirname "$0")/common.sh"

require_root
CURRENT="$TT_PREFIX/current"
[ -d "$CURRENT" ] || die "no current release found at $CURRENT."
PY="$(release_python "$CURRENT")"
[ -x "$PY" ] || die "current release virtualenv is missing."
command -v pg_dump >/dev/null 2>&1 || die "pg_dump is missing (install postgresql-client)."

mkdir -p "$TT_BACKUP_DIR"
chown "$TT_USER:$TT_USER" "$TT_BACKUP_DIR"
chmod 750 "$TT_BACKUP_DIR"

(cd "$CURRENT" && TT_SECRETS_FILE="$TT_SECRETS_FILE" TT_BACKUP_DIR="$TT_BACKUP_DIR" "$PY" - <<'PY'
import os
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url
from app import config

if not shutil.which("pg_dump"):
    print("backup: FAIL — pg_dump missing", file=sys.stderr)
    raise SystemExit(1)

out = Path(os.environ.get("TT_BACKUP_DIR", "/var/backups/taleb-talta"))
out.mkdir(parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
dest = out / f"taleb-talta-{stamp}-{secrets.token_hex(4)}.dump"
tmp = dest.with_suffix(".partial")

url = make_url(config.DATABASE_URL)
env = dict(os.environ)
env["PGDATABASE"] = url.database or "taleb_talta"
env["PGUSER"] = url.username or "postgres"
env["PGPASSWORD"] = url.password or ""
host = url.host or url.query.get("host")
if host:
    env["PGHOST"] = str(host)
port = url.port or url.query.get("port")
if port:
    env["PGPORT"] = str(port)
for key in ("sslmode", "sslrootcert", "sslcert", "sslkey"):
    if key in url.query:
        env["PG" + key.upper()] = str(url.query[key])

cmd = ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", "--file", str(tmp)]
try:
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print("backup: FAIL — pg_dump returned an error (details hidden)", file=sys.stderr)
        raise SystemExit(1)
    tmp.replace(dest)
    os.chmod(dest, 0o600)
    print(f"backup: PASS — {dest}")
finally:
    tmp.unlink(missing_ok=True)
PY
)
