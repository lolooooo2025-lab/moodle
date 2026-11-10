# Taleb Talta — جاهز على GitHub للرفع إلى Render

## المستودع والفرع

- المستودع: `https://github.com/lolooooo2025-lab/moodle`
- الفرع الجاهز للنشر: `arena/554c1e0a-moodle`
- مجلد التطبيق داخل المستودع: `taleb-talta/`
- ملف إعداد Render موجود في جذر المستودع: `render.yaml`

ملف `render.yaml` مضبوط على `rootDir: taleb-talta`، لذلك Render هيبني ويشغّل التطبيق من المجلد الصحيح تلقائيًا.

## قبل النشر على Render

1. اعمل حساب/مشروع على Neon.
2. خذ **Direct connection string** لقاعدة PostgreSQL.
   - استخدم الرابط المباشر، وليس رابط `-pooler`.
   - الشكل العام: `postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`
3. جهّز قيم المالك:
   - `TT_OWNER_PHONE`: رقم موبايل مصري من 11 رقم يبدأ بـ 010 أو 011 أو 012 أو 015 (بدون +20 وبدون مسافات).
   - `TT_OWNER_PASSWORD`: باسورد تجريبي قوي. لا تستخدم الباسورد الضعيف القديم.
   - `TT_VAPID_SUBJECT`: قيمة مثل `mailto:your-email@example.com`.

**لا تضع هذه القيم في GitHub ولا ترسلها في الشات.** ستدخلها في لوحة Render فقط.

## خطوات Render

1. افتح Render Dashboard.
2. اختار **New > Blueprint**.
3. اربط حساب GitHub لو لم يكن مربوطًا.
4. اختار المستودع: `lolooooo2025-lab/moodle`.
5. اختار الفرع: `arena/554c1e0a-moodle`.
6. Render سيقرأ `render.yaml` من جذر المستودع.
7. أدخل القيم المطلوبة:
   - `TT_DATABASE_URL`
   - `TT_OWNER_PHONE`
   - `TT_OWNER_PASSWORD`
   - `TT_VAPID_SUBJECT`
8. وافق على إنشاء الخدمة المجانية.
9. بعد انتهاء النشر، افتح:
   - `https://SERVICE-NAME.onrender.com/healthz`
   - المتوقع: `{"status":"ok"}`
10. افتح الصفحة الرئيسية وسجّل دخول المالك.

## ما الذي تم تجهيزه تلقائيًا؟

- خدمة ويب مجانية واحدة باسم `taleb-talta-demo`.
- منطقة `frankfurt`.
- Python `3.11.2`.
- تثبيت الاعتماديات من `requirements.lock.txt`.
- تشغيل التطبيق عبر `deploy/free-demo/start.py`.
- فحص صحة على `/healthz`.
- وضع التجربة `TT_DEMO_MODE=1`.
- الكوكيز الآمنة `TT_COOKIE_SECURE=1`.
- تقليل اتصالات قاعدة البيانات تناسب الخطة المجانية.
- توليد مفاتيح التجربة الخمسة تلقائيًا داخل Render.

## تنبيهات مهمة

هذه نسخة تجريبية مؤقتة وليست إطلاقًا حقيقيًا للطلبة:

- ملفات التطبيق على Render مجانية ومؤقتة؛ الملفات المرفوعة قد تختفي بعد إعادة التشغيل أو إعادة النشر.
- الخدمة تنام عند الخمول، وأول طلب بعدها قد يتأخر.
- لا يوجد cron worker مجاني دائم؛ يمكن تشغيل المهام يدويًا من لوحة الإدارة أو عبر كرون خارجي مجاني.
- النسخ الاحتياطية المحلية مقفولة في وضع التجربة.

تفاصيل أكثر داخل: `taleb-talta/FREE_DEMO.md`.

## الأمان

- لم يتم رفع `config/secrets.env` أو `config/production.env`.
- لم يتم رفع `storage/` أو قواعد البيانات أو ملفات المفاتيح.
- ملفات الإعداد المرفوعة هي أمثلة فقط بقيم بديلة.
- تم فحص الملفات المرشحة للرفع ضد القيم السرية المحلية قبل النشر.
