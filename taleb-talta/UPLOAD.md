# حزمة الرفع — طالب تالتة

هذه الحزمة مخصصة للرفع على سيرفر Linux VPS حديث (Ubuntu 24.04 / Debian 12 أو ما شابه)
وتحتوي على الكود + سكربتات النشر + إعدادات systemd وnginx. وهي **نظيفة من الأسرار**:
لا تحتوي على `config/secrets.env` ولا `config/production.env` ولا `storage/` ولا قاعدة البيانات.

## 1) المتطلبات

- Python 3.11 أو أحدث.
- PostgreSQL 14 أو أحدث، محلي أو خارجي، مع قاعدة بيانات ومستخدم جاهزين.
- دومين يشير إلى السيرفر (سجل A/AAAA) قبل إصدار شهادة HTTPS.
- صلاحيات root أو sudo.
- ملف الأسرار الخاص، يُنقل بشكل منفصل وآمن (SCP/SFTP)، ولا يوضع داخل مجلد عام.

## 2) فك الحزمة

```bash
unzip taleb-talta-upload.zip
cd taleb-talta
```

## 3) جهّز ملف الأسرار على السيرفر

انقل الملف الخاص إلى مسار خارج جذر الويب، مثل:

```bash
sudo install -m 600 /path/to/private.env /root/taleb-talta.env
```

الملف الحالي المحفوظ في مساحة العمل هو `config/production.env`. لا ترفعه داخل ZIP ولا تضعه في `/var/www`.
إذا كان الدومين مؤقتًا وكلمة سر المالك الحالية أقل من 12 حرفًا، فهذه نسخة تجريبية فقط؛
استخدم `--trial` صراحةً عند التثبيت. للإنتاج الحقيقي غيّر `TT_OWNER_PASSWORD` إلى كلمة قوية أولًا.

## 4) التثبيت الأول

```bash
sudo bash deploy/install.sh \
  --secrets /root/taleb-talta.env \
  --domain YOUR_DOMAIN \
  --tls-email admin@YOUR_DOMAIN
```

أضف `--trial` فقط للنشر التجريبي المؤقت. وأضف `--require-gemini` إذا كان مفتاح Gemini مطلوبًا عند الإطلاق.
إذا لم تمرر `--domain` سيقرأ السكربت اسم المضيف من `TT_PUBLIC_ORIGIN` داخل ملف الأسرار.

السكربت يقوم بالآتي:

- تثبيت حزم النظام المطلوبة (python3/venv/pip، postgresql-client، nginx، certbot عند طلب TLS).
- إنشاء مستخدم خدمة `taleb` ومسارات التشغيل والتخزين والنسخ الاحتياطية.
- إنشاء إصدار مستقل تحت `/opt/taleb-talta/releases/` مع بيئة بايثون خاصة به.
- فحص الإعدادات بدون طباعة الأسرار، وفحص عدم تسريب الأسرار في الملفات المخدومة.
- تشغيل خدمتي الويب والمهام المجدولة عبر systemd.
- إعداد nginx وإصدار شهادة Let's Encrypt عند تمرير `--tls-email`.

## 5) التحقق بعد التثبيت

```bash
systemctl status taleb-talta.service
systemctl status taleb-talta-cron.service
curl -fsS https://YOUR_DOMAIN/healthz
journalctl -u taleb-talta.service -n 100 --no-pager
```

## 6) التحديثات والنسخ الاحتياطية

قبل أي تحديث يؤخذ نسخة PostgreSQL احتياطية تلقائيًا، ثم تُشغّل الترحيلات بالترتيب الآمن:
`migrate_wave4.py` ثم `migrate_wave5.py` ثم `migrate_wave3.py`، وبعدها فحص المخطط الحي.

```bash
sudo bash deploy/update.sh --secrets /root/taleb-talta.env
```

للتجربة المؤقتة فقط أضف `--trial`. ولتغيير الدومين لاحقًا:

```bash
sudo bash deploy/update.sh \
  --secrets /root/taleb-talta.env \
  --domain NEW_DOMAIN \
  --tls-email admin@NEW_DOMAIN
```

نسخة احتياطية يدوية:

```bash
sudo bash deploy/backup.sh
```

الرجوع لإصدار سابق:

```bash
sudo bash deploy/rollback.sh
# أوحدد إصدارًا باسمه
sudo bash deploy/rollback.sh RELEASE_NAME
```

> الرجوع يعيد الكود فقط، ولا يعيد ترحيلات قاعدة البيانات تلقائيًا. استخدم النسخ الاحتياطية عند الحاجة.

## 7) المسارات الافتراضية

- الإصدار الحالي: `/opt/taleb-talta/current`
- الإصدارات: `/opt/taleb-talta/releases/`
- الأسرار: `/etc/taleb-talta/secrets.env` بصلاحيات `0600`
- التخزين والملفات المرفوعة: `/var/lib/taleb-talta/storage`
- النسخ الاحتياطية: `/var/backups/taleb-talta`

يمكن تغييرها بمتغيرات `TT_PREFIX`, `TT_ETC`, `TT_STATE`, `TT_BACKUP_DIR`, `TT_USER`, `TT_PORT` قبل تشغيل السكربتات.

## 8) ملاحظات أمنية وتشغيلية

- لا تضع الأسرار في Git أو في الشات أو داخل `app/static`.
- `TT_PUBLIC_ORIGIN` يجب أن يطابق الدومين النهائي HTTPS. عند تغيير الدومين حدّث الملف وأعد إعداد nginx/Shهادة.
- المنصة تفحص Origin لطلبات الكتابة اعتمادًا على `TT_PUBLIC_ORIGIN` عند تعيينه.
- الملفات المرفوعة خارج جذر الويب وتُقدّم عبر صلاحيات التطبيق فقط.
- Web Push الخارجي الحقيقي وHLS ingest/playback الحقيقي غير مُثبتين داخل بيئة الاختبار.
- لا يوجد payment gateway؛ التسوية يدوية. ولا توجد واجهة restore للنسخ الاحتياطية حتى الآن.
