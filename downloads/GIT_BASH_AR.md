# الخطوات كاملة من الصفر — رفع Taleb-Talta-V3 على GitHub (ويندوز + Git Bash)

اتبع الخطوات بالترتيب. كل بلوك يتنسخ زي ما هو في **Git Bash**.

---

## 1) ثبّت Git for Windows

من `https://git-scm.com/download/win` — أثناء التثبيت سيب الخيارات الافتراضية، وتأكد إن
**Git Credential Manager** معلّم عليه (هو اللي بيفتح المتصفح لتسجيل الدخول).

بعد التثبيت افتح **Git Bash** من قائمة Start.

---

## 2) نزّل ملف المشروع

افتح الرابط ده في المتصفح وهيحمّل الملف مباشرة:

```
https://raw.githubusercontent.com/lolooooo2025-lab/moodle/arena/554c1e0a-moodle/downloads/Taleb-Talta-V3.zip
```

الملف هيكون في مجلد **Downloads**.

---

## 3) فك الضغط في مجلد نضيف

```bash
cd ~/Downloads
powershell -NoProfile -Command "Expand-Archive -Path 'Taleb-Talta-V3.zip' -DestinationPath 'tt-v3' -Force"
cd tt-v3
ls
```

لازم تشوف في القائمة: `app` `config` `deploy` `docs` `tools` `render.yaml` `requirements.txt`

> لو أمر `powershell` فشل: كليك يمين على الـZIP في Explorer ← **Extract All**، وبعدين اعرف مكان المجلد بالأمر ده:
> ```bash
> find ~/Downloads -name render.yaml
> ```
> وادخل المجلد اللي طلعلك (بدون `/render.yaml` في الآخر) بأمر `cd`.

**تأكيد إنك في المكان الصح:**

```bash
ls render.yaml
```

لازم يطبع `render.yaml`. لو قال `No such file` **متكملش** — إنت في المجلد الغلط.

---

## 4) اضبط Git (مرة واحدة على الجهاز)

```bash
git config --global user.name "lolooooo2025-lab"
git config --global user.email "349031455+lolooooo2025-lab@users.noreply.github.com"
git config --global core.autocrlf false
git config --global core.longpaths true
git config --global credential.helper manager
git config --global credential.gitHubAuthModes browser
```

آخر سطرين هما اللي يخلوا تسجيل الدخول يتم **في المتصفح** مش في التيرمنال.

---

## 5) اتأكد مفيش ملفات أسرار

```bash
find . -name "*.env" ! -name "*.env.example"
```

لازم تطلع **فاضية**. لو طلعت حاجة، انقلها برّه المجلد.

---

## 6) اعمل الكوميت

```bash
git init
git add -A
git commit -m "Taleb Talta v3 - Render-ready app"
git branch -M main
git log --oneline -1
```

آخر أمر لازم يطبع سطر فيه رسالة الكوميت. لو قال `does not have any commits yet` متكملش.

---

## 7) اربط المستودع

```bash
git remote remove origin 2>/dev/null
git remote add origin https://github.com/lolooooo2025-lab/Taleb-Talta-V3.git
git fetch origin main
git merge --allow-unrelated-histories -X ours --no-edit origin/main -m "Merge initial commit"
```

> لو `git remote remove origin` قال `No such remote` تجاهله عادي.
> الدمج ده ضروري لأن المستودع فيها كوميتات أولية من GitHub؛ من غيره الرفع بيترفض.

---

## 8) ارفع (الدخول من المتصفح)

```bash
git push -u origin main
```

- هتفتح نافذة المتصفح: **Sign in to GitHub** ← **Authorize**.
- لو ما فتحش، هيطبع كود — افتح `https://github.com/login/device` واكتب الكود.
- **متكتبش أي token في الشات.**

---

## 9) اتأكد إن كل حاجة وصلت

```bash
git ls-files | wc -l
```

المتوقع **291**.

افتح في المتصفح: `https://github.com/lolooooo2025-lab/Taleb-Talta-V3`
لازم تشوف `render.yaml` و `app` و `deploy` في **جذر** المستودع.

---

## 10) النشر على Render

1. جهّز قاعدة بيانات مجانية على **Neon** وخُد **Direct connection string** (بدون `-pooler`).
2. Render ← **New** ← **Blueprint**.
3. اختر مستودع `Taleb-Talta-V3` والفرع `main`.
4. أدخل القيم في لوحة Render فقط:
   - `TT_DATABASE_URL` = رابط Neon المباشر
   - `TT_OWNER_PHONE` = رقم موبايل مصري 11 رقم يبدأ بـ 010/011/012/015
   - `TT_OWNER_PASSWORD` = الباسورد التجريبي
   - `TT_VAPID_SUBJECT` = `mailto:your-email@example.com`
5. **Deploy** واستنى لحد ما يخلص.
6. افتح `https://SERVICE-NAME.onrender.com/healthz` — المتوقع `{"status":"ok"}`.

> نسخة Render المجانية تجريبية: الخدمة بتنام عند عدم الاستخدام، والملفات المرفوعة مش دائمة.

---

## مشاكل شائعة

| المشكلة | الحل |
|---|---|
| `src refspec main does not match any` | مفيش كوميت محلي — ارجع لخطوة 6 وتأكد إن `git log` طبع كوميت |
| `cd: no such file or directory` | `ls ~/Downloads` أو `ls ~/OneDrive/Downloads` وشوف الاسم الصح |
| `Author identity unknown` | نفّذ بلوك خطوة 4 |
| `Updates were rejected` | نفّذ `git fetch` و `git merge` في خطوة 7 قبل الرفع |
| `remote origin already exists` | `git remote set-url origin https://github.com/lolooooo2025-lab/Taleb-Talta-V3.git` |
| `Authentication failed` | حدّث Git for Windows، أو استخدم `gh auth login` ← Login with a web browser |
| `git: 'credential-manager' is not a git command` | Git قديم — حدّثه من git-scm.com |

---

## ملف الأسرار

`render-secrets.env` يُسلَّم منفصلًا و**لا يُرفع على GitHub أبدًا**. تُنسخ قيم منه إلى لوحة Render فقط.
