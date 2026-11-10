# إعداد Neon لـ Taleb Talta

## الخطوات بتفاصيل

### 1. أنشئ حساب Neon مجاني

- اذهب إلى: https://neon.tech
- سجّل بحساب GitHub أو Google
- **مجاناً**: 0 GB RAM، 5 GB storage، دائماً متاح

### 2. أنشئ مشروع Neon

1. اضغط **"New project"**
2. اسم المشروع: `taleb-talta`
3. المنطقة: **EU Central (Frankfurt)** — أقرب لمصر
4. اضغط **"Create project"**

### 3. أنشئ Branch (قاعدة بيانات)

1. اذهب لمشروعك → **"Branches"**
2. اضغط **"New branch"**
   - Name: `main`
   - Compute: **Free** (0 GB)
3. اضغط **"Create branch"**

### 4. افحص Connection String

1. اذهب لـ **"Connection"** في sidebar
2. اختر **"Direct (unpooled)"** — asyncpg بيحتاج direct connection، مش pooled
3. Connection string:
   ```
   postgresql+asyncpg://USER:PASSWORD@ep-XXXXX-XXXXX.region-X.aws.neon.tech/taleb_talta?sslmode=require
   ```
4. احفظ هذا الـstring — ستحتاجه لاحقاً

### 5. طبق Schema على Neon

**الخيار A — باستخدام psql (أسهل):**

```bash
# ثبت psql إن لم يكن مثبتاً
sudo apt install postgresql-client   # Ubuntu/Debian

# طبق schema
psql "postgresql://USER:PASSWORD@ep-XXXXX-XXXXX.region-X.aws.neon.tech/taleb_talta?sslmode=require" \
  -f database/schema.sql

# طبق migrations
for mig in database/migrations/*.sql; do
  psql "postgresql://USER:PASSWORD@ep-XXXXX-XXXXX.region-X.aws.neon.tech/taleb_talta?sslmode=require" \
    -f "$mig"
done
```

**الخيار B — باستخدام Neon Console (بدون psql):**

1. اذهب إلى: https://console.neon.tech/YOUR_PROJECT_ID
2. اضغط **"SQL Editor"**
3. الصق `schema.sql` contents و execute
4. كرر لكل migration file

**الخيار C — باستخدام script مباشر:**

```bash
cd taleb-talta
bash setup_neon.sh
```

### 6. configure الـEnvironment Variables

في Netlify (Settings → Environment variables):

| المتغير | القيمة |
|---------|--------|
| `TT_NETLIFY` | `1` |
| `TT_DATABASE_URL` | `postgresql+asyncpg://USER:PASSWORD@HOST/DBNAME?sslmode=require` |
| `TT_PUBLIC_ORIGIN` | `https://your-site.netlify.app` |
| `TT_INTERNAL_ORIGIN` | `https://your-site.netlify.app` |
| `TT_OWNER_PHONE` | رقم الهاتف |
| `TT_OWNER_PASSWORD` | كلمة مرور قوية |
| `TT_CRON_TOKEN` | 32-hex random |
| `TT_STREAM_SECRET` | 32-hex random |
| `TT_VAPID_PRIVATE_KEY` | (اختياري) |
| `TT_VAPID_PUBLIC_KEY` | (اختياري) |
| `TT_DB_POOL_SIZE` | `5` |
| `TT_DB_MAX_OVERFLOW` | `2` |

### 7. تأكد من الـDatabase Tables

بعد تطبيق schema، تأكد من وجود هذه الجداول الأساسية:

```sql
-- 61 tables من schema.sql + 35 tables من migrations = 96 tables
SELECT count(*) FROM information_schema.tables
WHERE table_schema = 'public';
-- يجب أن يعطي: 96
```

### 8. إنشاء Owner Account

بعد نشر التطبيق على Netlify:

1. افتح موقعك
2. اذهب لـ `/register`
3. سجّل كـowner (أو استخدم صفحة admin)
4. أو استخدم الـAPI:
   ```bash
   curl -X POST https://your-site.netlify.app/api/auth/register \
     -H "Content-Type: application/json" \
     -d '{"phone":"01000000000","password":"SecurePass123","name":"مالك المنصة"}'
   ```

### 9. تفعيل Cron على Netlify

في Netlify (Settings → Functions → Scheduled functions):

```
*/5 * * * *  {"kind":"cron"}
```

### 10. التحقق

بعد النشر:

1. **تسجيل الدخول**: افتح الموقع وتأكد من تسجيل الدخول كـowner
2. **Cron**: اذهب لـ `/admin/tasks` وتأكد من أن المهام تنفذ
3. **Backup**: اذهب لـ `/admin/backups` وحاول عمل backup
4. **Upload**: اختر upload file وتأكد من رفع ملف صغير

---

## مسائل شائعة

### "connection refused" أو "timeout"

- تأكد من أن Branch قيد التشغيل (Free tier يتوقف بعد 5 دقائق غير نشط)
- استخدم **Direct (unpooled)** connection string، مش Pooled
- تأكد من `sslmode=require`

### "permission denied" لـ schema

- المستخدم يجب أن يكون owner أو superuser
- في Neon: افحص role عند إنشاء project

### "password authentication failed"

- أعد تعيين password من Neon Console
- أو أنشئ user جديد:
  ```sql
  CREATE USER taleb_talta WITH PASSWORD 'YOUR_PASSWORD';
  GRANT ALL PRIVILEGES ON DATABASE taleb_talta TO taleb_talta;
  ```

### "relation does not exist"

- تأكد من تطبيق schema.sql + جميع migrations
- شيك الجداول:
  ```sql
  \dt  -- في psql
  SELECT table_name FROM information_schema.tables WHERE table_schema='public';
  ```
