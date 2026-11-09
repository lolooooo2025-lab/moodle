# ربط دومين مخصص على Render — مع ضبط المشروع

## هل متاح على المجاني؟

أيوه. خطة الـworkspace المجانية **Hobby ($0 شهريًا)** بتشمل **custom domains** (2 مجانًا، وكل دومين زيادة بـ $0.25/شهر)، وRender بيصدر ويجدد شهادات **TLS مجانًا** ويحوّل HTTP لـ HTTPS تلقائيًا.

التكلفة الوحيدة هي **شراء الدومين نفسه** من أي مسجّل دومينات (Namecheap / GoDaddy / Cloudflare …). Render مش بيهدي دومينات.

> الدومين المخصص **لا يغيّر** حدود الخطة المجانية: الخدمة بتنام عند الخمول، والقرص مؤقت.

---

## 1) أضف الدومين في Render

1. لوحة Render ← اختر الخدمة `taleb-talta-demo`.
2. **Settings** ← انزل لقسم **Custom Domains**.
3. **+ Add Custom Domain** ← اكتب الدومين ← **Save**.

- لو أضفت الدومين الجذر `example.com`، Render بيضيف `www.example.com` تلقائيًا ويعمله redirect للجذر.
- لو أضفت `www.example.com`، بيضيف الجذر ويعمله redirect لـ www.

---

## 2) اضبط DNS عند مسجّل الدومين

**امسح أي سجل `AAAA`** (IPv6) من الدومين — Render بيستخدم IPv4.

| نوع الدومين | السجل المطلوب |
|---|---|
| دومين فرعي مثل `www.example.com` أو `app.example.com` | **CNAME** يشير إلى `taleb-talta-demo.onrender.com` |
| الدومين الجذر `example.com` | **ALIAS / ANAME** يشير إلى `taleb-talta-demo.onrender.com` |
| جذر لو المزوّد لا يدعم ALIAS/ANAME | **A record** إلى `216.24.57.1` |
| لو بتستخدم Cloudflare | لازم **CNAME** (مش A record) — والأفضل تقفل الـProxy (سحابة رمادية) وقت التحقق |

---

## 3) تحقّق من الدومين

ارجع لـ **Custom Domains** في Render واضغط **Verify**.

- لو فشل: استنى دقايق لحد ما DNS ينتشر وجرّب تاني.
- بعد النجاح Render بيصدر شهادة TLS.
- لو ظهر **502** أول مرة: استنى كام دقيقة، بيكون بيحدّث قواعد التوجيه.

---

## 4) ⚠️ خطوة إلزامية في المشروع: ضبط `TT_PUBLIC_ORIGIN`

التطبيق بيتحقق من الـOrigin في كل طلب كتابة (حماية CSRF)، وبيسمح **بهوست واحد فقط** هو المذكور في `TT_PUBLIC_ORIGIN`.

على `onrender.com` المشغّل بيضبطه تلقائيًا. لكن مع دومين مخصص:

- لو فضل `TT_PUBLIC_ORIGIN` على عنوان `onrender.com`، أي محاولة تسجيل دخول من الدومين الجديد هترجع **403 `err.csrf`**.

### الحل

من تبويب **Environment** في Render:

```
TT_PUBLIC_ORIGIN = https://example.com
```

- استخدم **الدومين النهائي** اللي المتصفح بيقف عليه فعلًا:
  - أضفت الجذر في Render ← استخدم `https://example.com`
  - أضفت www في Render ← استخدم `https://www.example.com`
- **بدون** شرطة مائلة في الآخر، وبدون مسار.
- بعدها **Manual Deploy ← Deploy latest commit**.

> بعد الضبط، تسجيل الدخول من عنوان `onrender.com` هيترفض (لأن المسموح هوست واحد).
> لو عايز الدومين المخصص بس، عطّل عنوان Render من:
> **Settings ← Custom Domains ← Render Subdomain ← Disabled**
> أو أضف في `render.yaml`:
> ```yaml
> renderSubdomainPolicy: disabled
> ```
> اعمل كده **بعد** ما تتأكد إن الدومين شغال.

---

## 5) تحقق نهائي

1. افتح `https://example.com/healthz` ← المتوقع `{"status":"ok"}`.
2. افتح `https://example.com/login` وسجّل دخول — لازم يشتغل بدون 403.
3. لو جالك `err.csrf`: راجع إن `TT_PUBLIC_ORIGIN` مطابق تمامًا للدومين اللي في شريط العنوان (www أو بدون www).

---

## ملخص التكاليف

| البند | التكلفة |
|---|---|
| خدمة Render مجانية | $0 |
| Custom domain على خطة Hobby | $0 (أول دومينين) |
| شهادة TLS | $0 |
| قاعدة Neon مجانية | $0 |
| **الدومين نفسه** | حسب المسجّل (عادة ~$10–15 سنويًا لـ .com) |
