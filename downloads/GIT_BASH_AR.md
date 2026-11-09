# رفع المشروع على GitHub باستخدام Git Bash (ويندوز)

الهدف: رفع محتويات `Taleb-Talta-V3.zip` إلى مستودع
[`lolooooo2025-lab/Taleb-Talta-V3`](https://github.com/lolooooo2025-lab/Taleb-Talta-V3) على الفرع `main`.

---

## 0) التجهيز

- ثبّت **Git for Windows** من `https://git-scm.com/download/win` (بيجي معاه Git Bash).
- نزّل `Taleb-Talta-V3.zip` من رابط التحميل المباشر — غالبًا هيكون في مجلد **Downloads**.
- **فك الضغط**: كليك يمين على الملف ← **Extract All** ← Extract.
  هيتكوّن مجلد اسمه `Taleb-Talta-V3` جوّاه الملفات مباشرة.

> لو مش عارف مكان الملف، افتح Git Bash واكتب `ls ~/Downloads` وشوف الاسم.

---

## 1) افتح Git Bash واضبط هويتك (مرة واحدة بس)

```bash
git config --global user.name "lolooooo2025-lab"
git config --global user.email "YOUR-GITHUB-EMAIL@example.com"
git config --global core.autocrlf false
git config --global core.longpaths true
```

- استخدم نفس الإيميل المسجّل على GitHub (أو إيميل `...@users.noreply.github.com` بتاعك).
- `core.autocrlf false` مهم علشان الملفات تفضل بنهايات أسطر Linux وما تبوظش على Render.

---

## 2) ادخل مجلد المشروع وتأكد إنك في المكان الصح

```bash
cd ~/Downloads/Taleb-Talta-V3
ls
```

لازم تشوف في القائمة:

```text
app  config  database  deploy  docs  tools  render.yaml  requirements.txt  README.md
```

> لو `render.yaml` مش موجود، يبقى إنت في المجلد الغلط — ادخل المجلد اللي جوّاه.

---

## 3) تأكد مفيش أي ملف أسرار قبل الرفع

```bash
find . -name "*.env" ! -name "*.env.example"
```

**لازم تطلع فاضية.** لو طلعت أي حاجة، انقلها برّه المجلد قبل ما تكمل.

---

## 4) اعمل الكوميت

```bash
git init -b main
git add -A
git commit -m "Taleb Talta v3 — Render-ready app"
```

> لو ظهر خطأ في `git init -b main` (نسخة Git قديمة)، استخدم:
> ```bash
> git init
> git branch -M main
> ```
> وبعدها كمّل باقي الأوامر عادي.

---

## 5) اربط المستودع وادمج الكوميت الأولي

المستودع فيها `README.md` أولي من GitHub، فالدمج بيتجنب رفض الرفع:

```bash
git remote add origin https://github.com/lolooooo2025-lab/Taleb-Talta-V3.git
git fetch origin main
git merge --allow-unrelated-histories -X ours --no-edit origin/main -m "Merge initial commit"
```

---

## 6) ارفع

```bash
git push -u origin main
```

- أول مرة هتفتح نافذة متصفح تطلب تسجيل الدخول لـ GitHub — سجّل دخول ووافق.
- **متكتبش أي token في الشات.** تسجيل الدخول بيتم في نافذة Git/المتصفح على جهازك.
- لو طلب باسورد في الشاشة السوداء ورفضه: نسخة Git قديمة. حدّث Git for Windows (بيجي مع Git Credential Manager) وكرر الأمر.

---

## 7) تأكد إن كل حاجة اترفعت

```bash
git ls-files | wc -l
```

المتوقع **291**.

وبعدها افتح في المتصفح:
`https://github.com/lolooooo2025-lab/Taleb-Talta-V3`

لازم تشوف `render.yaml` و`app` و`deploy` في **جذر** المستودع.

---

## 8) النشر على Render

1. Render ← **New** ← **Blueprint**.
2. اختار مستودع `Taleb-Talta-V3` والفرع `main`.
3. أدخل القيم السرية في لوحة Render فقط (من ملف `render-secrets.env` المنفصل).
4. `TT_DATABASE_URL` = رابط **Neon المباشر** (بدون `-pooler`).
5. بعد النشر افتح `https://SERVICE-NAME.onrender.com/healthz` — المتوقع `{"status":"ok"}`.

---

## تسجيل الدخول من المتصفح (مش من التيرمنال)

Git for Windows بييجي معاه **Git Credential Manager** اللي بيفتح المتصفح لتسجيل الدخول.

تحقق إنه موجود:

```bash
git --version
git credential-manager --version
```

لو الأمر التاني قال `command not found`، حدّث Git for Windows وسيب علامة **Git Credential Manager** أثناء التثبيت.

اضبطه مرة واحدة:

```bash
git config --global credential.helper manager
git config --global credential.gitHubAuthModes browser
```

وبعدها:

```bash
git push -u origin main
```

هتفتح نافذة المتصفح تلقائيًا: **Sign in to GitHub** ← **Authorize**. التيرمنال مش هيطلب باسورد.

لو المتصفح ما فتحش، هيطبع كود ولينك — افتح `https://github.com/login/device` واكتب الكود.

### بديل: GitHub CLI

```bash
gh auth login
```

اختار: `GitHub.com` ← `HTTPS` ← **Login with a web browser** ← انسخ الكود ← Enter ← المتصفح يفتح ← Authorize. وبعدها:

```bash
gh auth setup-git
git push -u origin main
```

> لا تكتب أي token في الشات ولا في ملف داخل المشروع.

---

## مشاكل شائعة

| المشكلة | الحل |
|---|---|
| `cd: no such file or directory` | مسار التحميل مختلف. جرّب `ls ~/Downloads` أو `ls ~/OneDrive/Downloads` |
| `render.yaml not found` | إنت في مجلد أبو المجلد المطلوب — ادخل خطوة جوّه |
| `Updates were rejected…` | نفّذ أمر الدمج في خطوة 5 قبل الرفع |
| `remote origin already exists` | `git remote set-url origin https://github.com/lolooooo2025-lab/Taleb-Talta-V3.git` |
| تحذيرات `LF will be replaced by CRLF` | غير مؤثرة بعد `core.autocrlf false` |
| `Authentication failed` | حدّث Git for Windows وكرر `git push` وسجّل دخول من النافذة |
