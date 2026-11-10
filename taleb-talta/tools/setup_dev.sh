#!/usr/bin/env bash
# Rebuild the local dev runtime (venv + real PostgreSQL + headless Chromium).
# Network access needed: pypi.org + registry.npmjs.org only.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=/home/user/ttvenv/bin/python
if [ ! -x "$PY" ]; then
  python3 -m venv /home/user/ttvenv
fi
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -r requirements-dev.txt
mkdir -p /home/user/tt_storage
TT_PGDATA="${TT_PGDATA:-/home/user/tt_pgdata}" "$PY" tools/devdb.py create
if [ ! -x /tmp/chromium-bin ]; then
  npm install --prefix /tmp/chromium-pack @sparticuz/chromium >/dev/null
  node - <<'JS'
const fs = require('fs'), zlib = require('zlib');
const base = '/tmp/chromium-pack/node_modules/@sparticuz/chromium/bin/';
fs.writeFileSync('/tmp/chromium-bin', zlib.brotliDecompressSync(fs.readFileSync(base + 'chromium.br')));
fs.chmodSync('/tmp/chromium-bin', 0o755);
fs.writeFileSync('/tmp/al2023.tar', zlib.brotliDecompressSync(fs.readFileSync(base + 'al2023.tar.br')));
JS
  mkdir -p /tmp/chromium-libs
  tar -xf /tmp/al2023.tar -C /tmp/chromium-libs
fi
echo "Dev runtime ready. Start the app with: bash run_dev.sh"
