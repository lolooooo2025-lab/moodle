#!/usr/bin/env bash
# Taleb Talta — one-command verification.
# Runs all static checkers, then the real-DB end-to-end suite (needs the dev
# server running: bash run_dev.sh). Exit non-zero on any failure.
set -uo pipefail
cd "$(dirname "$0")"
PY="${TT_PYTHON:-/home/user/ttvenv/bin/python}"
export PYTHONPATH="$(pwd)"
export TT_DATABASE_URL="${TT_DATABASE_URL:-postgresql+asyncpg://postgres:@/taleb_talta?host=/home/user/tt_pgdata}"

fail=0
run() {
  echo "------------------------------------------------------------"
  "$PY" "$@" || fail=1
}

echo "=== STATIC CHECKERS ==="
run tools/check_neon_env.py
run tools/check_i18n.py
run tools/check_served_secrets.py
run tools/check_fonts.py
run tools/check_enum_values.py
run tools/check_sql_injection.py
run tools/check_schema_columns.py

echo "------------------------------------------------------------"
echo "=== END-TO-END (real PostgreSQL + live server) ==="
if curl -s -o /dev/null http://127.0.0.1:8000/healthz; then
  "$PY" -c "import psycopg2" 2>/dev/null && true
  # clear rate limits so repeated verification logins are not throttled
  "$PY" - <<'PYEOF' 2>/dev/null || true
import asyncio
from app.core.db import get_sessionmaker, dispose_db
from sqlalchemy import text
async def m():
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM rate_limits")); await s.commit()
    await dispose_db()
asyncio.run(m())
PYEOF
  # Wave 4 must run first on older DBs: Wave 3 validates the full current metadata.
  run tools/migrate_wave4.py
  run tools/migrate_wave5.py
  run tools/migrate_wave3.py
  run tools/check_live_schema.py
  run tools/verify_wave0.py
  run tools/verify_wave1.py
  run tools/verify_wave2.py
  run tools/verify_wave3.py
  "$PY" - <<'PYEOF' 2>/dev/null || true
import asyncio
from app.core.db import get_sessionmaker, dispose_db
from sqlalchemy import text
async def m():
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM rate_limits")); await s.commit()
    await dispose_db()
asyncio.run(m())
PYEOF
  run tools/verify_wave4.py
  "$PY" - <<'PYEOF' 2>/dev/null || true
import asyncio
from app.core.db import get_sessionmaker, dispose_db
from sqlalchemy import text
async def m():
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM rate_limits")); await s.commit()
    await dispose_db()
asyncio.run(m())
PYEOF
  run tools/verify_wave5.py
  if [ "${TT_BROWSER:-1}" != "0" ] && [ -x /tmp/chromium-bin ]; then
    "$PY" - <<'PYEOF' 2>/dev/null || true
import asyncio
from app.core.db import get_sessionmaker, dispose_db
from sqlalchemy import text
async def m():
    async with get_sessionmaker()() as s:
        await s.execute(text("DELETE FROM rate_limits")); await s.commit()
    await dispose_db()
asyncio.run(m())
PYEOF
    run tools/browser_smoke.py
    run tools/browser_wave5.py
  elif [ "${TT_BROWSER:-1}" != "0" ]; then
    echo "FAIL: TT_BROWSER is enabled but /tmp/chromium-bin is missing (set TT_BROWSER=0 to skip deliberately)"
    fail=1
  fi
else
  echo "FAIL: dev server not running on :8000 (start with: bash run_dev.sh)"
  fail=1
fi

echo "============================================================"
if [ "$fail" -eq 0 ]; then
  echo "VERIFY: ALL PASSED"
else
  echo "VERIFY: FAILURES (see above)"
fi
exit $fail
