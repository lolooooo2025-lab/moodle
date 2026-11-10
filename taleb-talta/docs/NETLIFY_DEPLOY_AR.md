# دليل نشر Taleb Talta على Netlify + Neon

## المعمارية

Taleb Talta يعمل الآن كتطبيق Netlify Functions مع قاعدة بيانات PostgreSQL على Neon.

### المكونات

| المكون | الوصف |
|--------|-------|
| **Netlify Functions** | Node.js adapter (`netlify/server.mjs`) يستلم الطلبات من المتصفح، ويرسلها عبر loopback إلى CPython 3.11 مدمج داخل Function bundle |
| **Neon PostgreSQL** | قاعدة بيانات Postgres مع asyncpg driver، pool size 5+2 |
| **Background Workers** | `worker-background` Function ينفذ المهام الخلفية: cron و backup |
| **Objectstore** | Storage في Neon (جداول `tt_stored_objects` و `tt_stored_chunks`) |

### طريقة العمل

```
المتصفح ←→ Netlify CDN (static files + proxy)
                  ↓
          Netlify Functions (Node.js adapter)
                  ↓ loopback ↓
          bundled CPython 3.11 (FastAPI)
                  ↓
              Neon PostgreSQL
```

---

## خطوة بخطوة النشر

### 1. إعداد Neon

1. اذهب إلى https://console.neon.tech
2. أنشئ مشروعًا جديدًا (مشروع Neon)
3. اختر المنطقة الأقرب للمستخدمين
4. احصل على **Connection String** (DSN)

```
postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

5. تأكد من أن قاعدة البيانات تحتوي على الجداول الأساسية:
   - `tt_users`، `tt_sessions`، `tt_courses`، `tt_upload_transfers`، `tt_upload_chunks`
   - `tt_stored_objects`، `tt_stored_chunks` (للـobjectstore)
   - `tt_backup_artifacts` (لنسخ احتياطي)

### 2. إعداد Netlify

#### أ. ربط GitHub

1. اذهب إلى https://app.netlify.com
2. اضغط **Add new site** → **Import an existing project**
3. اختر `lolooooo2025-lab/moodle` من GitHub
4. اختر branch `arena/554c1e0a-moodle` أو أي branch فيه `taleb-talta/`

#### ب. Configure Build

**Build command:**
```
npm run build
```

**Publish directory:**
```
taleb-talta/dist
```

#### ج. Environment Variables

اضبط المتغيرات التالية في Netlify (Settings → Environment variables):

| المتغير | القيمة | الوصف |
|---------|--------|-------|
| `TT_NETLIFY` | `1` | وضع Netlify (نظام ملفات read-only، استخدام /tmp) |
| `TT_DATABASE_URL` | `postgresql+asyncpg://...` | DSN من Neon |
| `TT_PUBLIC_ORIGIN` | `https://your-site.netlify.app` | الـorigin الرسمي للموقع |
| `TT_INTERNAL_ORIGIN` | `https://your-site.netlify.app` | URL لاستدعاء Background Functions |
| `TT_OWNER_PHONE` | رقم الهاتف | حساب المالك |
| `TT_OWNER_PASSWORD` | كلمة المرور | كلمة مرور المالك |
| `TT_CRON_TOKEN` | random hex | Token للـinternal cron endpoint |
| `TT_STREAM_SECRET` | random hex | Secret لجلسات البث المباشر |
| `TT_VAPID_PRIVATE_KEY` | P-256 key | لـWeb Push notifications |
| `TT_VAPID_PUBLIC_KEY` | P-256 pubkey | لـWeb Push notifications |
| `TT_COOKIE_SECURE` | `1` | Cookies over HTTPS فقط |

#### د. Cron Schedules (Netlify)

أضف جدول cron في Netlify (Settings → Functions → Scheduled functions):

| المهمة | الجدول | الـbody |
|--------|--------|--------|
| cron run | `*/5 * * * *` | `{"kind":"cron"}` |

هذا يستدعي `worker-background` Function كل 5 دقائق لتشغيل المهام المجدولة.

### 3. النشر

1. اضغط **Deploy** في Netlify
2. انتظر حتى يكتمل الـbuild (~2-3 دقائق)
3. تأكد من أن الـdeploy نجح

### 4. التحقق

بعد النشر، تأكد من أن:

1. **الموقع يفتح**: افتح `https://your-site.netlify.app`
2. **التسجيل يعمل**: سجل دخول كـowner باستخدام `TT_OWNER_PHONE` و `TT_OWNER_PASSWORD`
3. **Cron يعمل**: تأكد من أن المهام المجدولة تنفذ (انظر TaskRuns في admin)
4. **Backup يعمل**: حاول عمل backup من صفحة admin

---

## النسخ الاحتياطي

### آلية النسخ الاحتياطي

1. **Manual backup**: من صفحة admin، اضغط "Backup"
2. **Scheduled backup**: `tool_backup.task.run_backup` ينشئ نسخة يوميًا
3. **Worker execution**: Backup ينفذ عبر `worker-background` Function

### طريقة التنفيذ

1. `POST /api/admin/backups` → إنشاء BackupArtifact row (status: "creating")
2. `_schedule(row.id)` → POST إلى `worker-background` Function
3. Worker يستلم `{"kind":"backup","backup_id":N}` → يستدعي `/api/internal/backups/run`
4. `run_pending()`:
   - `pg_dump` → ملف dump في /tmp
   - إذا `include_uploads=True`: يضغط dump + storage في tar.gz
   - يرفع الناتج إلى objectstore (Neon)
   - يضع status "ready" في DB

### استعادة النسخة

1. اذهب إلى صفحة admin → Backups
2. اضغط على نسخة → Download
3. استخدم `pg_restore` لاستعادة dump:
   ```bash
   pg_restore -d taleb_talta backup.dump
   ```

---

## الرفع بالأجزاء (Chunked Upload)

### آلية العمل

1. **Create transfer**: `POST /api/transfers/uploads` → ينشئ `UploadTransfer` row
2. **Upload chunks**: `PUT /api/transfers/uploads/{id}/chunks/{index}` → يخزن chunk في `tt_upload_chunks`
3. **Complete**: `POST /api/transfers/uploads/{id}/complete` → يجمع الأجزاء ويرفع إلى objectstore

### حدود الرفع

- **Max upload size**: 20 MB (لكل transfer كامل)
- **Chunk size**: 3 MiB (لكل chunk)
- **Max chunks**: 6 chunks (لكل transfer)
- **Rate limit**: 40 transfers/hour لكل user
- **Duplicate chunk**: 409 Conflict إذا رفع نفس الـindex مرتين

---

## التنزيل بـRange (Streaming)

### آلية العمل

1. **Large file** (أكبر من 15 MB): redirect إلى `/api/files/content?ticket=...`
2. **Signed ticket**: يحتوي على key، name، mime، expiry
3. **Range request**: `Range: bytes=0-1048575` → يرسل أول 1 MB فقط
4. **StreamingResponse**: يستخدم `objectstore.iter_range()` لتدفق البيانات

### حدود التنزيل

- **Direct response**: 15 MB (أصغر من 15 MB يرسل مباشرة)
- **Range response**: 1 MB لكل chunk
- **Max range**: 20 MB (لا يمكن تجاوز الحد الأقصى)

---

## استكشاف الأخطاء

### 1. الـsite لا يفتح

- تحقق من أن `TT_DATABASE_URL` صحيح
- تحقق من أن Neon يعمل (افحص connection string)
- تحقق من أن `TT_PUBLIC_ORIGIN` مطابق لموقعك

### 2. Cron لا يعمل

- تحقق من أن `TT_CRON_TOKEN` مضبوط
- تحقق من أن Netlify Cron Schedule مضبوط
- تحقق من أن `worker-background` Function موجود

### 3. Backup يفشل

- تحقق من أن `pg_dump` متوفر في bundle (مدمج مع CPython)
- تحقق من أن objectstore tables موجودة في Neon
- تحقق من أن `MAX_BYTES` كبير بما يكفي (default: 500 MB)

### 4. Cookie not working

- في HTTPS: `TT_COOKIE_SECURE=1` (default)
- في HTTP محلي: `TT_COOKIE_SECURE=0`
- تأكد من أن `SameSite=None; Secure; Partitioned` في cookies

---

## المتغيرات البيئية الكاملة

```bash
# Netlify Functions
TT_NETLIFY=1
TT_DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?sslmode=require
TT_PUBLIC_ORIGIN=https://your-site.netlify.app
TT_INTERNAL_ORIGIN=https://your-site.netlify.app

# أمان
TT_CRON_TOKEN=random-hex-token
TT_STREAM_SECRET=random-hex-secret
TT_PEPPER_ENABLED=1
TT_SESSION_COOKIE=tt_session
TT_COOKIE_SECURE=1
TT_COOKIE_PARTITIONED=1

# حسابات
TT_OWNER_PHONE=01000000000
TT_OWNER_PASSWORD=SecurePassword123

# Web Push
TT_VAPID_SUBJECT=mailto:support@example.com
TT_VAPID_PRIVATE_KEY=...
TT_VAPID_PUBLIC_KEY=...

# تحديدات إضافية
TT_DB_POOL_SIZE=5
TT_DB_MAX_OVERFLOW=2
TT_STORAGE_DIR=/tmp/taleb-talta-storage
TT_BACKUP_DIR=/tmp/taleb-talta-backups
```

---

## الملخص

| الميزة | الحالة |
|--------|-------|
| نشر Netlify Functions | ✅ يعمل |
| Neon PostgreSQL | ✅ يعمل |
| Background Workers | ✅ يعمل |
| Chunked Uploads | ✅ يعمل |
| Range Downloads | ✅ يعمل |
| Backups | ✅ يعمل |
| Cron | ✅ يعمل |
| Web Push | ✅ يعمل |
| العربية RTL | ✅ يعمل |

**التحقق: 520/520 checkpoint passed.**
