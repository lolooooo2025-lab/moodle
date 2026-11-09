# تسليم طالب تالتة — حزمة الكود

هذه الحزمة **نظيفة من الأسرار وبيانات التشغيل الخاصة**. لا تحتوي على
`config/secrets.env` ولا ملفات `.env` الحقيقية ولا `storage/` ولا قاعدة البيانات.

## 1) ملف الأسرار الآمن

- المثال الموجود داخل الحزمة: `config/secrets.env.example`
- الملف الحقيقي يفضل خارج مجلد الكود، مثل:
  `/etc/taleb-talta/secrets.env`
- الصلاحيات المطلوبة: المجلد الخاص `0700` والملف `0600`.
- متغيرات البيئة الحقيقية تتغلب على الملف. يمكن تحديد مكان الملف بـ
  `TT_SECRETS_FILE`.
- لا تضع كلمات السر أو مفاتيح API في الشات أو في Git أو داخل `app/static`.

القيم المطلوبة للإنتاج والتي لم يتم تضمينها في الحزمة:

- `TT_PUBLIC_ORIGIN` — الدومين الرسمي HTTPS.
- `TT_DATABASE_URL` — اتصال PostgreSQL الحقيقي.
- `TT_OWNER_PHONE` و`TT_OWNER_PASSWORD` — حساب المالك عند أول تشغيل فقط.
- `TT_GEMINI_API_KEY` — إذا كان مطلوبًا عند الإطلاق.
- `TT_VAPID_SUBJECT` — بريد التواصل الرسمي لـ Web Push.
- الأسرار المولدة: pepper/session/cron/stream/VAPID. يمكن توليدها محليًا،
  لكنها لا تُطبع في التقارير ولا تدخل الحزمة النظيفة.

## 2) فحص الإعدادات بدون كشف القيم

```bash
export TT_SECRETS_FILE=/etc/taleb-talta/secrets.env
python tools/check_production_config.py --require-gemini
```

الأمر يطبع **أسماء** القيم الناقصة فقط، ولا يطبع أي سر.

## 3) التشغيل

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export TT_SECRETS_FILE=/etc/taleb-talta/secrets.env
.venv/bin/python tools/check_production_config.py --require-gemini
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

في عملية منفصلة للمهام المجدولة:

```bash
export TT_SECRETS_FILE=/etc/taleb-talta/secrets.env
.venv/bin/python -m app.cron
```

ضع reverse proxy HTTPS أمام التطبيق، واجعله يضبط `Host` و`X-Forwarded-Proto`
ويتجنب تمرير forwarded headers مزيفة من العميل. عند تعيين `TT_PUBLIC_ORIGIN`
تستخدم المنصة الدومين المحدد في فحص Origin لطلبات الكتابة.

## 4) قاعدة البيانات

- قاعدة جديدة: شغّل التطبيق مرة أولى لإنشاء الجداول والبذور الأساسية، أو استورد
  `database/schema.sql` ثم شغّل التطبيق لإكمال البذور.
- قاعدة قائمة من الموجات السابقة: بالترتيب
  `tools/migrate_wave4.py` ثم `tools/migrate_wave5.py` ثم
  `tools/migrate_wave3.py`، وبعدها `tools/check_live_schema.py`.
- خذ نسخة احتياطية قبل أي ترحيل.

## 5) التحقق المحلي

ملفات التحقق مخصصة للتطوير/الاختبار فقط.Owner password يُقرأ من الملف الآمن،
وليس مكتوبًا في الكود. شغّلها على قاعدة اختبار، وليست على إنتاج.

```bash
bash tools/setup_dev.sh
bash run_dev.sh
bash verify.sh
```

آخر تحقق كامل مسجل في `docs/wave5-verify.log`، وفحص دخول المعاينة في
`docs/preview-login-verify.log`.

## 6) حدود معروفة

- Web Push الخارجي الحقيقي وHLS ingest/playback الحقيقي غير مُثبتين داخل Sandbox.
- لا يوجد payment gateway؛ التسوية يدوية كما طلبت المواصفات.
- لا يوجد restore UI للنسخ الاحتياطية حتى الآن.
- رفع ZIP للإضافات مؤجل لأسباب أمنية.
