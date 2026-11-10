# نشر المشروع على Taleb-Talta-V3

## 1) الوضع الحالي

| البند | الحالة |
|---|---|
| `Taleb-Talta-v2` (Fork من frappe/lms) | **اتحذفت** ✅ |
| `Taleb-Talta-V3` | **اتعملت** ✅ — مستودع عادي مش Fork، الفرع الافتراضي `main` |
| محتوياتها حاليًا | `README.md` فقط (Initial commit) |
| المشروع الجاهز | **291 ملف** — التطبيق في الجذر و`render.yaml` في الجذر |
| الكوميت المتحَضّر | جاهز ومبني فوق الكوميت الحالي بتاعك، ومستني إذن الرفع فقط |

## 2) العقبة المتبقية: صلاحية الكتابة

اتصال GitHub في الجلسة الحالية بيقدر يكتب على مستودع `moodle` فقط. الاختبارات الفعلية:

| الاختبار | على `moodle` | على `Taleb-Talta-V3` |
|---|---|---|
| إنشاء blob (صلاحية `contents=write`) | ✅ نجح | ❌ `403 Resource not accessible by integration` |
| `git push` | ✅ نجح | ❌ `403 Permission … denied` |

**السبب:** الرمز (token) المستخدم في هذه الجلسة اتصدر وقت بداية الجلسة مربوطًا بمستودع `moodle`. إضافة المستودع الجديد لتطبيق Arena على GitHub **لا تحدّث رمزًا صدر بالفعل**.

### الحل من داخل Arena

أعد ربط GitHub من إعدادات الاتصال في Arena (Disconnect ثم Connect)، واختَر عند التفويض مستودع `Taleb-Talta-V3` أو **All repositories**. بعدها ابعت رسالة جديدة وسأرفع الملفات فورًا.

بديلًا: افتح جلسة/محادثة جديدة على مستودع `Taleb-Talta-V3` نفسها.

> لأمانك: **لا ترسل أي token أو باسورد في الشات** — التفويض بيتم من واجهة Arena/GitHub فقط.

## 3) لو هترفعها بنفسك

### الطريقة الأسهل بدون أوامر — GitHub Desktop

1. ثبّت **GitHub Desktop** وسجّل دخول بحسابك.
2. **File ← Clone repository** ← اختر `Taleb-Talta-V3`.
3. فك ضغط `Taleb-Talta-render-upload.zip`.
4. انسخ **محتويات** المجلد (وليس المجلد نفسه) داخل مجلد المستودع المستنسخ، واقبل استبدال `README.md`.
5. في GitHub Desktop: اكتب رسالة كوميت ← **Commit to main** ← **Push origin**.

### بالأوامر — السكربت الجاهز

من داخل المجلد بعد فك الضغط:

```bash
gh auth login          # مرة واحدة فقط
bash publish-v3.sh
```

السكربت:

- يرفض العمل لو لقى أي ملف `.env` خاص داخل المجلد.
- ينضّف `__pycache__` و`storage` قبل الرفع.
- يدمج الكوميت الأولي الموجود في المستودع بدل ما يكتب فوقه بالقوة (تم اختبار المسار بنجاح).
- يرفع كل الملفات على فرع `main`.

### يدويًا بالكامل

```bash
cd path/to/unzipped-folder
git init -b main
git add -A
git commit -m "Taleb Talta v3"
git remote add origin https://github.com/lolooooo2025-lab/Taleb-Talta-V3.git
git fetch origin main
git merge --allow-unrelated-histories -X ours --no-edit origin/main -m "Merge initial commit"
git push -u origin main
```

## 4) بعد الرفع مباشرة

1. تأكد أن **`render.yaml` في جذر المستودع** — وليس داخل مجلد فرعي.
2. Render: **New ← Blueprint** ← اختر `Taleb-Talta-V3` ← الفرع `main`.
3. أدخل القيم من ملف `render-secrets.env` في **لوحة Render فقط**.
4. `TT_DATABASE_URL`: استخدم رابط **Neon المباشر** (بدون `-pooler`).
5. بعد النشر افتح `https://SERVICE-NAME.onrender.com/healthz` — المتوقع `{"status":"ok"}`.

## 5) ملف الأسرار

`render-secrets.env` يظل **خارج GitHub تمامًا**: لا يُرفع مع المشروع، ولا يوضع داخل مجلد الرفع. تُنسخ قيم منه إلى لوحة Render فقط.
