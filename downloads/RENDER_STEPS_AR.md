# نشر Taleb-Talta-V3 على Render — خطوة بخطوة

المتطلبات: مستودع `Taleb-Talta-V3` فيها الملفات و`render.yaml` في الجذر. **مفيش كارت بنكي مطلوب** للخطة المجانية.

---

## 1) قاعدة البيانات على Neon (مجاني)

1. افتح `https://neon.com` وسجّل حساب (يمكن بحساب GitHub).
2. **New Project**:
   - الاسم: `taleb-talta`
   - المنطقة: **AWS eu-central-1 (Frankfurt)** — قريبة من منطقة الخدمة على Render.
3. بعد إنشاء المشروع، من **Connection Details / Dashboard**:
   - اختار **Connection string**
   - **اقفل خيار Pooled connection** — لازم الرابط **المباشر (Direct)**.
4. انسخ الرابط، شكله كده:
   ```
   postgresql://USER:PASSWORD@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```

> مهم: لو الرابط فيه `-pooler` في اسم الهوست، ده الرابط المجمّع وهي فشل مع التطبيق. استخدم المباشر.
> التطبيق بيحوّل الرابط تلقائيًا لصيغة asyncpg، فمش محتاج تعدّل فيه حاجة.

---

## 2) حساب Render وربط المستودع

1. افتح `https://render.com` ← **Get Started** ← سجّل بـ **GitHub**.
2. لو المستودع **Private**، لازم تدي Render صلاحية عليها:
   أثناء اختيار المستودع اضغط **Configure account / Manage access** ← اختر
   `Taleb-Talta-V3` (أو All repositories) ← **Save**.

---

## 3) إنشاء الخدمة من الـBlueprint

1. من لوحة Render: **New +** ← **Blueprint**.
2. اختر مستودع **`Taleb-Talta-V3`** والفرع **`main`**.
3. Render هيقرا `render.yaml` تلقائيًا ويعرض خدمة واحدة:
   - الاسم: `taleb-talta-demo`
   - النوع: Web Service / Python
   - الخطة: **Free**
   - المنطقة: **Frankfurt**
4. اكتب اسم للـBlueprint (مثلاً `taleb-talta`) واضغط **Apply / Deploy**.

---

## 4) المتغيرات المطلوبة

Render هيطلب منك 4 قيم بس (الباقي متولّد تلقائيًا):

| المتغير | القيمة |
|---|---|
| `TT_DATABASE_URL` | رابط Neon **المباشر** من خطوة 1 |
| `TT_OWNER_PHONE` | رقم موبايل مصري من 11 رقم يبدأ بـ 010 / 011 / 012 / 015 |
| `TT_OWNER_PASSWORD` | باسورد المالك (التجريبي بتاعك) |
| `TT_VAPID_SUBJECT` | `mailto:your-email@example.com` |

القيم دي بتتولد تلقائيًا بواسطة Render ومش محتاجة تدخّل:
`TT_PASSWORD_PEPPER` — `TT_SESSION_SECRET` — `TT_CRON_TOKEN` — `TT_STREAM_SECRET` — `TT_VAPID_PRIVATE_KEY`

**اختياري:** لتفعيل المساعد الذكي، ضيف من تبويب **Environment**:
`TT_GEMINI_API_KEY` = مفتاحك.

> **لا تضبط `TT_PUBLIC_ORIGIN` يدويًا** على Render — التطبيق بياخد عنوان الخدمة تلقائيًا.
> لو ضبطته على دومين غلط، تسجيل الدخول هيفشل بسبب حماية CSRF.

---

## 5) تابع النشر

- البناء بياخد كام دقيقة (`pip install -r requirements.lock.txt`).
- عند التشغيل، التطبيق بيعمل تهيئة الجداول وحساب المالك تلقائيًا.
- لو ظهر في اللوج:
  ```
  free-demo: missing environment variables: ...
  ```
  يبقى في قيمة ناقصة — ضيفها من **Environment** واعمل **Manual Deploy**.

---

## 6) اتأكد إن الخدمة شغالة

1. افتح رابط الخدمة من أعلى لوحة Render، شكله:
   `https://taleb-talta-demo.onrender.com`
2. جرّب:
   ```
   https://taleb-talta-demo.onrender.com/healthz
   ```
   المتوقع: `{"status":"ok"}`
3. افتح `/login` وسجّل دخول برقم الموبايل والباسورد اللي دخلتهم.
4. هتلاقي شريط تنبيه إن دي **نسخة تجريبية** — ده متوقع في وضع الديمو.

---

## 7) حدود الخطة المجانية (مهم تعرفها)

| الحد | التأثير |
|---|---|
| الخدمة بتنام بعد ~15 دقيقة بدون زيارات | أول طلب بعدها بياخد ~30–60 ثانية |
| القرص مؤقت | الملفات المرفوعة (فيديوهات/صور) بتضيع مع إعادة النشر أو التشغيل |
| مفيش worker أو cron مجاني | المهام المجدولة تتشغّل يدويًا من `/admin/tasks` |
| 750 ساعة مجانية شهريًا | كفاية لخدمة واحدة تجريبية |
| قاعدة Neon | البيانات محفوظة ومستقلة عن Render (1 جيجا تخزين / 100 CU-hours شهريًا) |

النسخ الاحتياطي مقفول في وضع الديمو لأن القرص مؤقت.

### تشغيل المهام المجدولة (اختياري)

من خدمة كرون مجانية زي cron-job.org:

- Method: `POST`
- URL: `https://YOUR-SERVICE.onrender.com/api/cron/run`
- Header: `X-Cron-Token: <قيمة TT_CRON_TOKEN من تبويب Environment>`
- كل 15 دقيقة.

خلي بالك إن ده بيصحّي الخدمة ويستهلك من الساعات المجانية.

---

## مشاكل شائعة

| المشكلة | السبب / الحل |
|---|---|
| `missing environment variables` | قيمة من الأربعة ناقصة — ضيفها واعمل Manual Deploy |
| فشل الاتصال بقاعدة البيانات | استخدم رابط Neon **المباشر** بدون `-pooler` |
| تسجيل الدخول بيرفض | متضبطش `TT_PUBLIC_ORIGIN` يدويًا؛ امسحه واعمل Deploy |
| البناء فشل في التثبيت | تأكد إن `PYTHON_VERSION=3.11.2` موجودة وإن `requirements.lock.txt` في الجذر |
| `502` أو تحميل بطيء أول مرة | الخدمة كانت نايمة — استنى دقيقة وحدّث |
| Render مش شايف المستودع | ادي تطبيق Render صلاحية على `Taleb-Talta-V3` من Configure account |
| الملف اتغيّر ومش بيتحدث | اعمل **Manual Deploy ← Deploy latest commit** |
