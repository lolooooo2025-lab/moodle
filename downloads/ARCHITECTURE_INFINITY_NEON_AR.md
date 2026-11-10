# تقييم فكرة: InfinityFree للواجهة + Neon للباك إند

## الحقائق الثلاث الحاكمة

### 1) Neon قاعدة بيانات — لكن عندها Data API

المتصفح لا يفتح اتصال TCP بـ Postgres. لكن **Neon Data API** واجهة REST over HTTPS
متوافقة مع PostgREST، تقبل JWT وتطبّق Row-Level Security، ومناسبة للتطبيقات التي
تعمل من المتصفح مباشرة بدون سيرفر وسيط.

- https://neon.com/docs/data-api/overview
- https://neon.com/docs/connect/choose-connection

**تحذير رسمي من Neon:** الـData API ليس لها طبقة صلاحيات خاصة بها؛ كل الحماية عبر
GRANT و RLS. أي جدول بدون RLS يصبح مكشوفًا لكل من يملك الرابط.

- https://neon.com/docs/data-api/get-started

### 2) InfinityFree لا يصلح كـ CDN للرسومات

الـhotlinking محظور تقنيًا، حتى بين subdomains بتاعة نفس الحساب. لا يمكن رفع الصور هناك
وعرضها على موقع مستضاف في مكان آخر.

- https://forum.infinityfree.com/t/create-my-own-cdn-with-my-subdomain/76786
- https://forum.infinityfree.com/t/hi-can-i-host-a-rest-api-using-infintyfree/53006

### 3) InfinityFree يشغّل PHP فقط

لا Python، لا Node.js، لا WebSockets. ولا يمكن استدعاء صفحاته من سيرفر آخر لأن
نظام الحماية يتأكد أن الزائر متصفح حقيقي.

- https://forum.infinityfree.com/t/question-regarding-of-supported-website-formats/116751
- https://forum.infinityfree.com/t/can-i-use-websocket-in-my-website-using-node-js/100630

**لكن** مسموح صراحةً استضافة HTML + JavaScript فقط، وأن يتصل الـJS بخدمة خارجية:

- https://forum.infinityfree.com/t/socket-io-backend-hosting-on-another-site/92668

---

## المعمارية الممكنة فعلًا

```
المتصفح
  │
  ├── HTML/CSS/JS + الصور  ← InfinityFree (نفس الدومين، بدون hotlink)
  ├── تسجيل الدخول + JWT    ← Neon Auth
  └── قراءة/كتابة البيانات  ← Neon Data API + RLS في Postgres
```

بدون سيرفر Python، وبدون بطاقة بنكية.

### الثمن: إعادة كتابة التطبيق

التطبيق الحالي FastAPI يرندر صفحات Jinja على السيرفر، ومعه جلسات وCSRF ونظام
صلاحيات ومهام مجدولة وSSE وWeb Push ورفع ملفات. التحويل إلى «static + Data API» يعني:

| الجزء | ما يحدث له |
|---|---|
| صفحات Jinja | إعادة كتابتها كواجهة JavaScript |
| الصلاحيات (capabilities) | إعادة بنائها كـ RLS policies داخل Postgres |
| الجلسات وCSRF | تستبدل بـ Neon Auth + JWT |
| البث المباشر / HLS | غير ممكن على InfinityFree |
| Web Push | يحتاج سيرفر يرسل الإشعارات |
| المهام المجدولة | تحتاج خدمة خارجية |
| رفع الفيديوهات | حدود InfinityFree: 10 ميجا للملف، وممنوع توزيع الفيديو |
| النسخ الاحتياطي | يحتاج آلية جديدة |

يعني عمليًا مشروع جديد، وليس تعديلًا على القائم.

---

## بدائل تحافظ على الشغل الحالي

| الخيار | بطاقة؟ | يحتفظ بكل الميزات؟ | ملاحظات |
|---|---|---|---|
| تيلدا + Render | بطاقة مسبقة الدفع مجانية | ✅ | كل التجهيزات جاهزة بالفعل |
| FastAPI على Back4app أو Railway | لا | ✅ تقريبًا | موارد محدودة جدًا في المجاني |
| جهازك + Cloudflare Tunnel + Neon | لا | ✅ كامل | الموقع يقف لو الجهاز قفل |
| InfinityFree + Neon Data API | لا | ❌ | إعادة كتابة شاملة |
