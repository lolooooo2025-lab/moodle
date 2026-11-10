# ربط Neon بالمشروع محليًا (`.env.local`)

## الحالة

| الخطوة | الحالة |
|---|---|
| تثبيت Neon CLI | ✅ تم — الإصدار 9.3.0 |
| تسجيل الدخول `neon login` | ⛔ متعذر من بيئة العمل هنا |
| `neon init` / `neon deploy` | ⛔ نفس السبب |
| تهيئة كود التطبيق لقراءة `.env.local` | ✅ تم — 24 فحص ناجح + الحزمة الكاملة ALL PASSED |

**سبب التعذر:** بيئة العمل هنا مسموح لها بالاتصال بنطاقات محددة فقط (GitHub / npm / PyPI).
الوصول لـ `console.neon.tech` مرفوض تمامًا، بينما `api.github.com` يرد طبيعي — يعني المشكلة في الشبكة مش في حسابك.
ولذلك تسجيل الدخول والتفعيل لازم يتمّا **على جهازك**.

> لم تُطبع أي سلسلة اتصال في المحادثة، ولا يتم طباعتها من الكود.

---

## نفّذ ده على جهازك

من داخل مجلد المشروع (اللي جوّاه `app/` و `render.yaml`):

```bash
npm i -g neon@latest
neon login
neon init -y --org-id org-red-mouse-20851240 --project-id old-mountain-87254720 \
  --branch production --services postgres,auth,object-storage,realtime
neon deploy
```

- `neon login` هيفتح المتصفح — سجّل دخول وأكمِل.
- `neon deploy` هيكتب القيم في `.env.local`.
- **متبعتش محتوى الملف في الشات.**

---

## التطبيق بيستخدم الملف إزاي

أضفت `app/neon_env.py` وبيتشغّل تلقائيًا مع إعدادات التطبيق ومع مشغّل Render:

| مفتاح Neon | بيتستخدم كـ |
|---|---|
| `DATABASE_URL_UNPOOLED` | **`TT_DATABASE_URL`** (الأولوية) |
| `DATABASE_URL` | بديل احتياطي فقط |
| `NEON_AUTH_*` / `NEON_REALTIME_*` / `AWS_*` / `NEON_BRANCH` | بتتحط في البيئة ومتاحة، لكن التطبيق لسه مش بيستخدمها |

### ليه الرابط غير المجمّع؟

التطبيق بيستخدم **asyncpg** اللي بيعتمد على prepared statements، وده بيكسر مع
رابط Neon المجمّع (`-pooler` / pgbouncer). فالكود بياخد `DATABASE_URL_UNPOOLED`
وبيرفض يشتغل لو المتاح بس هو الرابط المجمّع، وبيطلع رسالة واضحة.

كمان بيحوّل الرابط تلقائيًا:
`postgres://` ← `postgresql+asyncpg://`، و`sslmode` ← `ssl`، وبيشيل `channel_binding`.

### الأولوية

```
متغيرات البيئة الحقيقية  >  TT_NEON_ENV_FILE  >  .env.local  >  .env  >  config/secrets.env
```

يعني قيم لوحة Render دايمًا هي اللي بتكسب.

### الأمان

- `.env` و `.env.*` مستثنيين من Git بالفعل — **مش هيتـرفعوا**.
- الكود بيرجّع **أسماء المفاتيح فقط** ومش بيطبع القيم أبدًا.

---

## على Render

**مش محتاج الملفات دي خالص.** حط `TT_DATABASE_URL` في لوحة Render على رابط Neon
**المباشر** وخلاص — المشغّل بيحوّله لوحده. الملفات دي للتشغيل المحلي بس.

---

## التحقق

```bash
python tools/check_neon_env.py
```

24 فحص باستخدام قيم وهمية فقط، وبقى جزء من `verify.sh`.
