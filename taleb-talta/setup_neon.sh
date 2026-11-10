#!/usr/bin/env bash
# Taleb Talta — Neon إعداد دليل
# هذا السkript ينشئ قاعدة بيانات Neon جاهزة للتطبيق.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "=== Taleb Talta Neon Setup ==="
echo ""

# 1. تحقق من neon CLI
if ! command -v neon &>/dev/null; then
    echo "[ERR] neon CLI مش مثبت."
    echo "  ثبته:  npm install -g neon"
    echo "  أو:    curl -fsSL https://neon.tech/install | bash"
    exit 1
fi

echo "[1/5] neon CLI: $(neon --version)"

# 2. إنشاء مشروع Neon جديد (إن لم يكن موجوداً)
if ! neon init --skip-verify 2>/dev/null; then
    echo "[2/5] neon init — أنشئ مشروع جديد"
    neon init --skip-verify
fi

PROJECT_ID="$(neon projects list 2>/dev/null | head -1 | awk '{print $1}')"
if [ -z "$PROJECT_ID" ]; then
    echo "[ERR] لا يوجد مشروع Neon. أنشئ واحد من: https://console.neon.tech"
    exit 1
fi
echo "[2/5] مشروع Neon: $PROJECT_ID"

# 3. إنشاء قاعدة بيانات (branch)
BRANCH="main"
neon branches list 2>/dev/null | grep -q "$BRANCH" || neon branches create "$BRANCH" --name "$BRANCH"
echo "[3/5] Branch: $BRANCH"

# 4. استخراج بيانات الاتصال
neon env pull 2>/dev/null || true
if [ ! -f "$ROOT/.env.local" ] && [ ! -f "$ROOT/.env" ]; then
    echo "[4/5] كتابة .env.local"
    neon env pull
fi

# 5. تطبيق schema + migrations
echo "[5/5] تطبيق schema و migrations"

# تأكد من وجود pg
if ! command -v psql &>/dev/null; then
    echo "[WARN] psql مش مثبت. ثبت postgresql-client:"
    echo "  Ubuntu/Debian: sudo apt install postgresql-client"
    echo "  macOS:         brew install libpq"
    exit 1
fi

# استخرج DATABASE_URL من .env.local أو .env
DB_URL="$(grep '^DATABASE_URL=' "$ROOT/.env.local" 2>/dev/null | cut -d= -f2- ||
          grep '^DATABASE_URL=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- ||
          grep '^DATABASE_URL_UNPOOLED=' "$ROOT/.env.local" 2>/dev/null | cut -d= -f2- ||
          grep '^DATABASE_URL_UNPOOLED=' "$ROOT/.env" 2>/dev/null | cut -d= -f2-)"

if [ -z "$DB_URL" ]; then
    echo "[ERR] DATABASE_URL مش موجود في .env أو .env.local"
    echo "  ادخل بيانات Neon من: https://console.neon.tech/$PROJECT_ID"
    exit 1
fi

# تطبيق schema.sql
echo "  → schema.sql"
psql "$DB_URL" -f "$ROOT/database/schema.sql" 2>&1 | grep -v "^SET\|^CREATE\|^GRANT\|^ALTER" | head -5 || true

# تطبيق migrations
for mig in "$ROOT"/database/migrations/*.sql; do
    name="$(basename "$mig")"
    echo "  → migrations/$name"
    psql "$DB_URL" -f "$mig" 2>&1 | grep -v "^SET\|^CREATE\|^GRANT\|^ALTER\|^BEGIN\|^COMMIT" | head -3 || true
done

# 6. إنشاء owner account
echo ""
echo "=== إنشاء حساب Owner ==="
echo "أدخل بيانات الحساب:"
read -rp "Phone: " OWNER_PHONE
read -rsp "Password: " OWNER_PASSWORD
echo ""

# 7. تحديث secrets.env
SECRETS="$ROOT/config/secrets.env"
echo "" >> "$SECRETS"
echo "# Neon (generated $(date -u +%Y-%m-%dT%H:%M:%SZ))" >> "$SECRETS"
echo "TT_DATABASE_URL=$DB_URL" >> "$SECRETS"
echo "TT_OWNER_PHONE=$OWNER_PHONE" >> "$SECRETS"
echo "TT_OWNER_PASSWORD=$OWNER_PASSWORD" >> "$SECRETS"
chmod 600 "$SECRETS"

echo ""
echo "=== الإعداد مكتمل ==="
echo "  قاعدة البيانات: Neon ($PROJECT_ID / $BRANCH)"
echo "  Connection: $DB_URL"
echo "  secrets: $SECRETS (0600)"
echo ""
echo "التالي:"
echo "  1. افتح https://console.neon.tech/$PROJECT_ID"
echo "  2. افحص connection string (Pooling: direct)"
echo "  3. ابدأ التطبيق: cd taleb-talta && npm run build && npx netlify functions:serve"
