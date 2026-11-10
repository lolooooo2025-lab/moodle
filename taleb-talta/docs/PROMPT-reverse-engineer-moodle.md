# PROMPT — Reverse-engineer ALL of Moodle, then build "Taleb Talta" as an Egyptian-Arabic web platform

> **How to use:** attach `moodle.zip`, `Taleb Talta Logo.png`, and `Taleb Talta specification.md` to your model, then paste everything below verbatim. It is fully self-contained.

---

## 0) ROLE & MISSION

You are a **senior platform architect + full-stack engineer + Egyptian Arabic copywriter**. You have shipped large Moodle-based and Moodle-inspired systems and you know Moodle's architecture the way you know your own codebase.

Two-stage mission:

**Phase 1 — RESEARCH.** Open `moodle.zip` and reverse-engineer **the whole of Moodle** — not only its security layer, but its **plugin architecture, admin panel, customization system, feature modules, data model, and extension workflow**. Produce a written analysis with file paths.

**Phase 2 — BUILD.** Implement an original platform, **Taleb Talta**, that reproduces Moodle's *architectural power* — plugin-extensible, admin-configurable, feature-complete — but with its own domain, schema, brand, and code, and with **Egyptian colloquial Arabic as its native language**.

**Deliver working, running code in verifiable waves.** An outline, a mockup, or a TODO is failure. Each wave must be runnable end-to-end before you start the next.

---

## 1) ATTACHMENTS & EXISTING CODEBASE

### 1.1 You will receive

| File | What it is |
|---|---|
| `moodle.zip` | A Moodle source tree. **Your research material.** |
| `Taleb Talta Logo.png` | The official logo. Extract its exact colours programmatically. |
| `Taleb Talta specification.md` | The functional spec (11 items). Read it fully. |

**Extract the logo colours programmatically** (Python + PIL → quantize → pick dominant saturated hues). Do not eyeball hex values. Expected families: a blue (~`#1564C7`), a cyan (~`#2BB4FB`/`#36C8FC`), an amber (`#F9BC4B`/`#FDC034`), a deep navy (`#0A368B`/`#0D1A34`), plus neutrals (`#F7F8FB`, `#EEF0F6`, `#B1B8D3`, `#496C98`). Report the *measured* values.

### 1.2 The existing Taleb Talta repository (do not start from zero)

A partial implementation already exists. **Extend it — do not rewrite it from scratch and do not discard it.**

```
/workspace/taleb-talta/
├─ admin-panel/            # PHP 8.1 + MySQL, no framework, no build step
│  ├─ admin/               # 18 staff pages (dashboard, courses, lessons, exams,
│  │                       #   library, users, audit, broadcasts, campaigns, reports,
│  │                       #   purchases, streams, stickers, ai_knowledge, security, …)
│  ├─ api/index.php        # JSON API router (tolerates /x and /api/v1/x)
│  ├─ includes/            # auth.php, security.php, db.php, functions.php, bootstrap.php, layout/
│  ├─ config/config.php    # server-side secrets live ONLY here
│  ├─ storage/             # uploads (protected)
│  ├─ tools/               # install.php, dbcheck.php, create_owner.php
│  └─ assets/              # css/js/img
├─ database/schema.sql     # 37 tables
├─ docs/                   # specification, api-contract, DEPLOYMENT, moodle-security-research
├─ tools/                  # static checkers (schema columns / SQL params / ENUM / fonts / secrets)
└─ verify.sh               # one command that checks everything
```

Current state: **34 PHP files / ~6 050 lines / 37 tables**. The **staff admin panel and the API exist**; the **student-facing web portal does not exist yet**; the **plugin/customization system does not exist yet**.

**Before writing anything**, audit what is actually there and what actually works. Do not assume the existing code is correct — several known defects were already found in it (see §12). Verify it against a real database, fix what is broken, then extend.

---

## 2) PROJECT BRIEF

**Taleb Talta** is an Arabic-first educational platform for Egyptian high-school students (third year):

- **One web platform**, two areas sharing one core:
  - **Student area** — courses, lessons, library, exams, chat, messages, notifications, AI assistant, profile, purchase requests.
  - **Staff area (admin)** — content management, moderation, users, divisions, purchases, broadcasts, live streams, reports, audit, security settings, plugin management.
- Everything Arabic-Egyptian (§3), RTL by default.
- PHP 8.1 + MySQL, no framework, **no build step** (the host cannot run Node).

**Live target (already provisioned):**

| | |
|---|---|
| Public domain | `taleb-talta.ct.ws` |
| API base (no prefix) | `https://taleb-talta.ct.ws/` |
| API base (fallback) | `https://taleb-talta.ct.ws/api/v1/` |
| MySQL host | `sql204.infinityfree.com` (resolves only from inside that network) |
| MySQL database | `if0_43272844_taleb_talta` |
| MySQL user | `if0_43272844` |
| Hosting | InfinityFree free tier — see §10 for hard constraints |

---

## 3) LANGUAGE REQUIREMENT — EGYPTIAN COLONIAL ARABIC (a first-class requirement)

**This is not a localisation detail. It is a product decision, and it must show everywhere a human reads words.**

The platform speaks **عامية مصرية** — the way people actually talk in Egypt. Not Modern Standard Arabic, not a stiff literal translation. Think of how a good Egyptian school/education product would talk to a student or a parent on WhatsApp.

### 3.1 Where it applies — every user-visible string

- UI labels, buttons, placeholders, empty states, tooltips, help text.
- Validation messages and **all error messages** (the most important place — nobody wants "خطأ في التحقق من الحقول").
- Success / warning / failure toasts.
- Emails (registration, purchase, ban, password reset, broadcast).
- Push-style notifications and the Friday campaign.
- AI assistant answers (§6.10).
- Admin panel copy (a teacher or supervisor reads it too).
- Page titles, breadcrumbs, and the 404/403/500 pages.

### 3.2 Rules

1. **Frame the sentence in Egyptian; keep technical nouns in MSA where they are clearer.** Egyptian apps do this in real life: the noun is often MSA, the *sentence around it* is colloquial. e.g. «الامتحان خلص، نتيجتك اتحسبت» — not «تم الانتهاء من الامتحان بنجاح».
2. **Never use machine-translated stiff MSA.** If a string sounds like it came out of a translator, rewrite it.
3. **No transliterated English where an Arabic word exists** — except product names that users already know (فيسبوك، يوتيوب، PDF، Excel).
4. **No emojis in product copy.** Use them in chat only, and sparingly.
5. **Numbers**: use Western Arabic numerals (0-9) consistently — Egyptian users type them that way.
6. **No religious/superstitious phrasing, no hyperbole** ("يا حبيبي", "ماشي يا فندم" overused, "الأسرع في مصر"). Keep it warm but professional — like a good school supervisor, not a street vendor.

### 3.3 Reference transformations (illustrative, not exhaustive)

| Stiff MSA ❌ | Egyptian ✅ |
|---|---|
| تم تسجيل الدخول بنجاح | تمام، إنت داخل |
| هل أنت متأكد من حذف هذا العنصر؟ | متأكد إنك عايز تمسح العنصر ده؟ هيترسمي |
| لم يتم العثور على النتائج | مالقيتش نتايج بالرقم ده — اتأكد من الرقم |
| يرجى إدخال رقم صحيح من فضلك | الرقم مش مظبوط، جرّب تاني |
| تم حفظ التغييرات | اتحفظ ✅ |
| كلمة المرور الحالية غير صحيحة | كلمة السر الحالية غلط |
| لا يوجد اتصال بالإنترنت | مفيش نت — اتأكد من الاتصال وكمّل |
| تم إرسال رسالتك | رسالتك اتبعتت |
| حسابك موقوف | حسابك متوقف دلوقتي — كلّم الدعم |
| Your session has expired | الجلسة خلصت، سجّل دخول تاني |
| المحتوى قيد المراجعة | المحتوى راجع من المشرف، هيتنشر قريب |

### 3.4 Implementation requirements

- **All strings live in a language file** — `lang/ar.php` returning a key→string array (Moodle's `lang/ar/*.php` pattern). **No user-visible string may be hard-coded in a `.php` page, an API response, or a JS file.** A checker must fail the build if a hard-coded Arabic literal is found outside `lang/`.
- Structure the language layer so a second language can be added later without touching code.
- Arabic typography: RTL document direction, correct line-height for Arabic (≥ 1.7), `font-feature-settings` for Arabic ligatures where useful, numerals with `font-variant-numeric`, no Latin/Arabic bidi bugs (test mixed strings like "الامتحان 3 يوم 12:30 م" and "User: أحمد").
- **Fonts:** self-host a real Arabic TTF (e.g. Cairo) via `@font-face` with `font-display: swap`, with `woff2` + `ttf` sources. Never rely on the system Arabic font, and never load fonts from a CDN (see §7.5).

### 3.5 The AI assistant must speak Egyptian too

Its system prompt must require: Egyptian colloquial answers, mandatory source citations, and the exact refusal phrase `لا يوجد في المصادر` when the retrieved sources do not answer the question. (§6.10)

---

## 4) PHASE 1 — REVERSE-ENGINEER ALL OF MOODLE

Read `moodle.zip` and map the following, **with file paths and line references**. For each: the pattern, the invariant it protects, and how it breaks if omitted.

### 4.1 The plugin/module architecture (the most important part)

How a Moodle feature becomes a plugin. Map concretely:

- The canonical directory layout of a plugin: `version.php`, `db/install.xml` (or `install.php`), `db/upgrade.php`, `db/access.php`, `db/events.php`, `db/services.php`, `db/tasks.php`, `settings.php`, `lib.php`, `lang/<lang>/<plugin>.php`, `classes/`, `templates/`, `amd/`, `pix/`.
- How a plugin declares: name, version, dependencies, release date, maturity, supported DB engines.
- **The install/upgrade lifecycle**: `xmldb_install` → DB schema → capability registration → event observer registration → language pack install → cron task registration → cache purge → "upgrade needed" version bump.
- How the **admin plugin browser** finds, lists, validates, installs, upgrades, and disables plugins.
- How plugins register: navigation/menu entries, settings nodes, events/observers, web services (API), scheduled tasks, search areas, reports, blocks, dashboard blocks, grading, badges, filters, editors, auth providers, enrolment providers, repository providers.
- The **plugin API surface**: callbacks, `after_config`, `before_config`, form/validation classes, event classes, capability providers.
- **Moodle's "extend a core concept" pattern**: e.g. adding a question type to `quiz`, an activity to a course, a block to a dashboard, a grade item to the gradebook.

**Deliverable:** a written spec of the Taleb Talta plugin architecture (§5.4) derived from this.

### 4.2 Core subsystem catalogue

Map each subsystem's architecture and list the tables it owns:

- **Users & identity** — account creation, profiles, custom profile fields, preferences, cohorts/groups, guest access, suspension, deletion vs anonymisation, GDPR/privacy API, notification preferences.
- **Authentication** — auth plugins, login-by-email, self-registration + approval, password policy, "forgot password" flow, account confirmation, 2FA, SSO hooks, login sequencing.
- **Course structure** — categories, courses, course formats, sections, activities, visibility/dates ("available from/to"), enrolment (self, manual, cohort, guest, pay-for-access), completion tracking, tags, competencies, groups, timetables.
- **Content authoring** — the **Lesson module** (sections/pages with content items: text, file, link, question; branching; completion conditions), plus page/label, URL, book/PDF, SCORM, assignment, forum, quiz, workshop, choice, database, feedback, H5P.
- **Quizzes** — question bank (question types: MCQ single/multi, true-false, short answer, matching, essay, numeric, drag-drop, ordering), attempts, randomisation, time limits, marks, feedback, review options, grading.
- **Communication** — forums (posts, threads, ratings, subscriptions, moderation), messaging (contacts, conversations, read state, notifications, blocking), chat (channels, participants, messages), comments.
- **Grading** — grade items, gradebook (user report, grader report, category totals, weights, scales, grades, feedback, regrading), competency framework, badges/criteria, outcome.
- **Files & media** — repository plugins, file areas, private vs public files, file serving gateway, thumbnails, quota, references, trashcan, file licences.
- **Calendar & scheduling** — events, subscriptions, agenda, upcoming events.
- **Notifications & messaging framework** — notification classes, preferences, digests, providers, mobile pushes.
- **Administration** — site settings tree, admin tools, reports, logs, scheduled tasks (cron), backups/restore, upgrade, site administration sections, "site status".
- **Customization** — themes (base/parent/child theming), colour schemes, dashboards & blocks, toolbars, navigation, language packs, custom fields, site branding (logo, colours, name), "my courses"/dashboard configuration.
- **Search & indexing** — global search, indexing, filters.
- **Data & analytics** — reporting, exports (CSV/Excel), data privacy, logs.

### 4.3 Admin panel architecture

Map how Moodle's admin area is structured: navigation tree, settings pages and their persistence, tool pages, plugins admin, reports, and how a site administrator extends it. Note which patterns make an admin panel feel "complete" vs "thin".

### 4.4 Phase-1 outputs — three documents

1. **`docs/moodle-analysis.md`** — subsystem-by-subsystem map, each item with Moodle **file paths + line numbers**; a table *Moodle pattern → what it protects → Taleb Talta equivalent*; and an explicit **"we deliberately deviate"** list with reasons (Moodle serves 1 000 institutions and 5 million users; Taleb Talta serves one school and ~1 000 students — copy the invariants, not the scale).
2. **`docs/feature-matrix.md`** — every Moodle feature area → Taleb Talta equivalent → status (`exists in the current repo` / `to build` / `out of scope, with reason`) → priority → which wave (§6) it lands in.
3. **`docs/lang-ar.md`** — a proposed Egyptian-Arabic glossary: the ~300 highest-frequency UI terms in MSA→Egyptian, plus the tone rules of §3, ready to be turned into `lang/ar.php`.

### 4.5 ⚠️ Licensing constraint — hard requirement

Moodle is **GPLv3**.

- **Do NOT copy Moodle source code into Taleb Talta.**
- Reverse-engineer the *architecture, invariants, and algorithms*, then write **original code** from your own understanding.
- When reproducing a Moodle algorithm (e.g. a hashing scheme, a capability-resolution order), write it yourself from the description — do not paste Moodle's file.
- Short quotations (≤ 15 lines) in the analysis docs are fine, clearly marked as GPL Moodle code with its source path.
- Keep an "inspired by" note in the architecture doc. No code copying.

---

## 5) PHASE 2 — TARGET ARCHITECTURE (web platform)

### 5.1 Stack & constraints

| | |
|---|---|
| Stack | PHP 8.1 + MySQL, **no framework**, **no Composer at runtime**, **no build step** |
| Rendering | Server-side PHP templates + a small vanilla-JS layer (ES modules). No bundler, no npm. |
| CSS | One hand-written stylesheet driven by CSS custom properties for theming (§5.5). |
| Assets | **Self-hosted only.** No CDN, no Google Fonts, no external JS. Reason: offline capability, privacy, and CSP integrity. |
| Offline / installability | Ship a `manifest.webmanifest` + a service worker for PWA install and offline caching of **public/static assets only** (§12 trap 12). |
| DB access | PDO, `ATTR_EMULATE_PREPARES = false`. Never concatenate SQL. |
| Routing | A front-controller with `.htaccess` rewriting; the base path is computed at runtime from `SCRIPT_NAME` (never hard-coded `/`). |
| Layout | Arabic RTL everywhere. Shared header/footer/nav with a role-aware menu. |
| Scale | ~1 000 students, ~50 staff. PHP is sufficient; do not add Redis/queues. Scheduled tasks = a cron hit to `api/cron.php` (InfinityFree offers cron jobs). |

### 5.2 The two areas

- `/` — student portal: dashboard, courses, lesson player, library, exams, chat, messages, notifications, AI assistant, profile, purchases.
- `/admin` — staff area: dashboard, content, moderation, users, divisions, purchases, broadcasts, campaigns, live streams, reports, audit, security settings, plugin manager, site settings, theme designer.
- Both share the core: session handling, capability checks, audit, i18n, layout.

### 5.3 API contract

- Write **`docs/api-contract.md` before implementing the endpoints.** It is the source of truth for both areas and for any future client.
- Versioned, JSON envelope `{success, message, data}`; error codes documented per endpoint.
- Staff UI calls the same API where sensible — one implementation, two consumers.
- The contract must include the pagination, filtering, and sorting conventions.

### 5.4 The plugin system (the heart of "add any feature")

This is what makes Taleb Talta a *platform* rather than an app. Design it to mirror Moodle's model:

```
plugins/<type>/<name>/
├─ version.php          # name, version, dependencies, release date, maturity
├─ manifest.json        # machine-readable metadata (types, permissions, tables)
├─ db/install.php       # returns SQL statements
├─ db/upgrade.php       # version → version steps
├─ db/access.php        # capability definitions
├─ db/events.php        # events + observers
├─ db/services.php      # API/web-service exposure
├─ db/tasks.php         # scheduled tasks
├─ settings.php         # admin settings nodes
├─ lib.php              # callbacks, navigation entries, capability helpers
├─ lang/ar.php          # strings
├─ classes/             # PHP classes (PSR-4 style, own autoloader)
├─ templates/           # renderable templates
├─ assets/              # css/js
└─ pix/                 # icons
```

Requirements:

- **Own autoloader** (no Composer) mapping `plugins/<type>/<name>/classes/` → namespace, plus `core/` → `core/` classes.
- **Plugin installer**: an admin page that accepts a ZIP, validates `manifest.json` + `version.php`, checks dependencies, runs `db/install.php`, registers capabilities/events/tasks, adds its menu entries and settings, and records the install. Show the result (success/failure + the exact error) — never a blank page.
- **Uninstall**: remove menu/settings/hooks; **never drop user data silently** — offer "keep data" (default) or "purge" (owner-only, audited).
- **Upgrade path**: `db/upgrade.php` with ordered steps keyed on the installed version; the platform shows "plugins need upgrade" in the admin panel, like Moodle.
- **Plugin types to support at launch:** `block` (dashboard block), `tool` (admin tool page), `report` (a new report), `local` (feature module: e.g. a new course activity), `qtype` (a new exam question type), `theme` (a visual theme), `filter` (content filter), `auth` (login provider), ` enrol` (enrolment method), `repository` (file source).
- **Built-in examples** (must ship, proving the system works): one `tool` (e.g. "مدير النسخ الاحتياطي"), one `block` (e.g. "الجدول الدراسي"), one `report` (e.g. "تقرير الحضور"), one `local` feature module (e.g. "سؤال اليوم" — a daily-question activity).
- **Every plugin action is audited** and gated by a capability.

### 5.5 Customization & theming

- **Site settings**: platform name, logo upload, favicon, primary/secondary colours, contact info, registration toggle, maintenance mode, feature flags per plugin.
- **Themes**: a CSS-variable theme layer. Ship ≥ 3 themes (e.g. "كحلي", "فاتح", "محايد"), selectable in the admin panel, with per-role override capability. A theme defines colours, radius, density, font, dark/light — not duplicated CSS.
- **Per-entity custom fields**: user fields (e.g. رقم髄髓 /Guardian) and course fields (e.g. numeral of lessons) defined by admins in a settings screen, rendered on the relevant forms and filters. (Moodle's custom fields model.)
- **Dashboard**: configurable blocks per role, add/remove/reorder, persisted per user.
- **Menus**: admin-managed navigation menu items (label, URL, icon, target role, order).

### 5.6 Internationalisation

`lang/ar.php` + a `t()` helper with fallback to the key. Never hard-code a user-visible string (§3.4).

---

## 6) PHASE 3 — WHAT TO BUILD (waves)

Build in waves. **Each wave is merged only when it runs.** Ship a status line per wave in your final report.

### Wave 0 — Foundation (must be first)

- Layout engine + RTL + theme variables + `t()` + language file.
- Session management (§7.2), `sesskey`, capability system (§7.3), audit log (§7.6).
- Login / logout / registration (Egyptian validation messages) / forgot-password / profile.
- Core navigation for student + staff, with role-aware menus.
- The plugin system skeleton (§5.4) with **one** trivial plugin proving install works.

### Wave 1 — Courses, lessons, library

- Course categories, courses, sections, and the **Lesson player** (pages of content items: text, file, link, question; completion tracking; progress bar).
- The **shared library** with a **moderator approval** workflow (submit → review → approve/reject with a reason), and each student's **private space** (see §6.11 for where it lives on the web).
- Enrolment by division; course visibility; availability dates.

### Wave 2 — Exams & grading

- Question bank (MCQ single/multi, true/false, short answer, matching, numeric) with an **admin question editor**.
- Attempts: time limit, one attempt or N, auto-grading for objective types, manual grading for short answer.
- **Correct answers must never reach the browser before submission.** Grade on the server.
- The gradebook: per-course marks, totals, ranking, export to CSV/Excel.
- Exam result review with per-question explanation (the spec's "مناقشة التوضيحية": a discussion thread attached to a specific question, with a reference chip that deep-links exam → discussion).

### Wave 3 — Communication

- **Forum-style discussion** (threads, posts, replies, subscriptions, moderation).
- **Messages** (1:1, contact list, read/unread, blocking, reporting).
- **Chat**: private 1:1, group, and **division channel**; attachments, stickers, live polling of messages (AJAX/long-poll, no websockets needed on this host).
- **Profanity filter** on all user text (chat, messages, posts, forum). Policy: mask + warn, and escalate: 1st warning, 2nd warning, 3rd → **30-day ban** covering chat **and** evaluations. A banned user attempting to log in notifies the admin.
- Moderation queue: reported content → staff review → approve/remove/warn/ban, all audited.

### Wave 4 — Admin, customization, plugins

- Full admin panel (the 18 existing pages, completed and made consistent), plus: site settings tree, plugin manager, theme designer, custom-field builder, dashboard builder, menu builder.
- Reports: enrolments, activity, grades, usage, audit — with CSV/Excel export.
- Scheduled tasks (cron) for digests, cleanup, backup.

### Wave 5 — Money, broadcasts, live

- **Paid courses**: price + manual settlement + admin confirmation. **No payment gateway.** Student requests → support confirms → access unlocks. Server-enforced (`403 PAID_CONTENT_LOCKED`), never a UI-only lock.
- **Live streaming**: stream metadata, scheduling, audience targeting (all / course / division), a player page, live chat alongside, and a **publish key visible only to the owner** (stored encrypted, never returned to non-owners).
- **Targeted notifications**: compose to role / division / course / individual; per-user read state; the Friday campaign as a special weekly broadcast shown to everyone identically, with an archive.

### Wave 6 — AI assistant, calendar, polish

- **Gemini RAG assistant** (§6.10), the AI knowledge base managed in the admin panel, and the admin's ability to seed it from approved course content.
- Calendar/agenda, upcoming deadlines.
- Accessibility pass, performance pass, Egyptian copy pass, RTL bug sweep.

### 6.11 The student's "private space"

The spec says the approved material is copied to *the student's own machine* and can be shared out. On the web this becomes:
- A **private area per student** (server-side, access-controlled) holding their approved copies, downloadable and shareable, plus an offline copy in the browser via **IndexedDB** (with a "save for offline" action and an "offline library" screen).
- The online copy must be permission-checked per student — never a public URL.

---

## 7) PHASE 4 — SECURITY (Moodle-grade; these are the point of the exercise)

### 7.1 Passwords

- **PBKDF2-HMAC-SHA256**, 310 000 iterations, **256-bit random salt per user**, plus a server-side **pepper** in `config/config.php` (never in the DB, never in any served file).
- ⚠️ **PHP has no `PASSWORD_PBKDF2` constant** (only `PASSWORD_BCRYPT`, `PASSWORD_ARGON2I/ID`). Use `hash_pbkdf2('sha256', $material, $salt, $iterations, 64, true)`.
- Compare with `hash_equals()` — never `==`.
- Verification must tolerate a pepper being enabled *after* passwords exist (try peppered and unpeppered material).
- Policy: ≥ 12 chars, ≥ 4 character classes, must not equal the phone number, expiry, reuse history.
- Lockout: failed attempts per account **and** per IP; thresholds; duration; admin override; every lockout audited.

### 7.2 Sessions

- Server-side sessions. Cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` (the app's real path).
- **`session_regenerate_id(true)`** on login and on any privilege change.
- **Idle timeout (30 min) and absolute timeout (12 h)** — separate, both enforced.
- **Hijack detection**: store a fingerprint (hash of IP + User-Agent); on mismatch → destroy the session, log `session.hijack_detected` at `critical`, force re-login.
- `sesskey` generated per session, **rotated on login**, required on every state-changing request.
- Revocation on logout, password change, ban, and admin "force logout".

### 7.3 Authorization — capabilities, not role checks

- A `TT_CAPABILITIES` catalogue + `tt_can()` / `tt_require_capability()`, exactly Moodle's model.
- Owner-only destructive actions (course purge, plugin purge, security settings, live-stream key) enforced **in the API**, never in the UI.
- Every panel write requires a valid `sesskey`; every AJAX write also validates `Origin`/`Referer`.

### 7.4 CSRF & output

- `sesskey` on every mutating request (forms and AJAX).
- Escape on output: `htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8')`.
- Rich text: sanitise against a small allow-list (`b, i, u, strong, em, p, br, ul, ol, li, a[href]`, `a[href^="https?://"]` only) and strip everything else.
- **No string-concatenated SQL.** Bound parameters only.
- Typed input helpers with explicit bounds (`input_text`, `input_int`, `input_email`, `input_phone`).

### 7.5 Headers, CSP, and the browser

- **CSP** without `unsafe-inline`: use per-request nonces for inline scripts/styles. `default-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- `Strict-Transport-Security` (with `includeSubDomains`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` minimising camera/mic/geolocation.
- **No CDN and no third-party scripts** — that keeps the CSP tight and the platform private.
- `Cache-Control: no-store` on every authenticated page and every API response (never cache private data in the browser cache).
- **Cookie `Secure`** + HSTS = the browser enforces the pinned-host trust; there is no certificate-pinning story in a browser (see §7.9).

### 7.6 Audit log

- Append-only `audit_log`: actor, role, action, entity, before/after JSON, IP, user agent, severity.
- Severity is an `ENUM` (`info` / `notice` / `warning` / `critical`) so the DB rejects invalid values.
- Log: login success/failure, lockouts, capability denials, moderation decisions, purchases, broadcasts, plugin install/uninstall, settings changes, session revocation.

### 7.7 File handling

- Uploads: validate the **real** MIME with `finfo` (never trust the extension or the client's `Content-Type`), enforce an extension allow-list, enforce a size cap, and store files **outside any web-servable path**.
- Serve every file through an **authorised gateway** (Moodle's `pluginfile.php` pattern): check the session, check the capability, check that the requester owns/has access to the parent entity, then stream it with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and a forced `Content-Type: application/octet-stream` for anything that is not a known-safe image type. **Never `include`/`require` an uploaded file, never let it execute.**
- Quota per user and total; reference integrity; a trashcan with a scheduled purge task.

### 7.8 Rate limiting & abuse

- Limit by IP and by user: login attempts, registration, messages, posts, chat sends, uploads, AI queries, and password-reset requests.
- A honeypot field + a minimum time-to-submit on the registration form.

### 7.9 What changes from a native app (be explicit)

There is **no APK**, so there is nothing to harden on the device. The equivalent protections move server-side:

| Native-app control | Web equivalent |
|---|---|
| No secrets in the APK | **No secret in any served file** — a checker greps every `.php`/`.js`/`.html`/`.css` for the pepper, the Gemini key, the DB password. |
| Certificate pinning | HSTS + a strict CSP + `Secure` cookies + `no-store` on private responses |
| Root/emulator detection (advisory) | Rate limiting + lockout + honeypot + audit signals; the browser gives us no trustworthy signal, so the server decides from behaviour |
| Encrypted local token store | Server-side session + `HttpOnly`/`Secure`/`SameSite` cookie; the token is never readable by JavaScript |
| `allowBackup=false` | No private data in `localStorage`/`sessionStorage`; private data lives in IndexedDB only for the offline library, and is wiped on logout |
| Screenshots blocked (`FLAG_SECURE`) | Not applicable; mitigate by not rendering sensitive pages in a cacheable frame (`frame-ancestors 'none'`) |

### 7.10 No secrets in served files

Add a checker that scans the entire served tree for every secret defined in `config/config.php` and **fails** if one appears in any file that a browser can fetch. Also assert that `config/` and `tools/` are unreachable over HTTP.

---

## 8) PHASE 5 — BRAND & DESIGN

- **Typography**: self-host Cairo (real TTF/woff2, verified — see §12 trap 11) via `@font-face`, used for all text.
- **Colour**: use the logo-extracted palette as CSS custom properties; build light + dark variants; define `primary`/`secondary`/`accent`/`surface`/`text` roles, not ad-hoc hex values in components.
- **Components**: a small consistent UI kit (buttons, inputs, cards, tables, badges, modals, toasts, empty states, skeletons) — one definition, reused everywhere.
- **Arabic quality**: RTL correctness everywhere, no bidi bugs, comfortable line-height, readable tables (RTL tables are a common mess — get them right), correct focus rings, min tap target 44px, contrast ≥ 4.5:1, full keyboard navigation.
- **Density**: the staff area is dense (tables, filters, inline actions); the student area is calm and roomy.

---

## 9) PHASE 6 — DATA MODEL

Extend the existing **37-table** schema. Cover, at minimum:

`users` · `sessions` · `login_attempts` · `password_reset_tokens` · `user_devices` · `divisions` · `courses` · `course_sections` · `lessons` · `lesson_items` · `lesson_progress` · `course_students` · `library_items` · `user_library` · `exams` · `questions` · `question_options` · `exam_attempts` · `attempt_answers` · `grades` · `discussion_threads` · `discussion_messages` · `channels` · `channel_members` · `messages` · `stickers` · `profanity_words` · `content_reports` · `moderation_actions` · `purchases` · `live_streams` · `broadcasts` · `notifications` · `friday_campaigns` · `ai_knowledge` · `ai_sessions` · `ai_messages` · `audit_log` · `security_settings` · `ip_allowlist`
**plus** (new for Moodle parity): `plugins` · `plugin_settings` · `plugin_events` · `themes` · `custom_fields` · `custom_field_values` · `blocks` · `dashboard_blocks` · `menu_items` · `site_settings` · `scheduled_tasks` · `tags` · `cohorts` · `cohort_members` · `notifications_read` · `attachments` · `grades_config`

Rules:
- InnoDB, `utf8mb4_unicode_ci`, `DATETIME` timestamps, soft delete where the spec implies it.
- **Every FK target table must be created before the referencing table** (a wrong order = errno 150 and the entire import fails).
- **Every column used in a PHP `INSERT`/`UPDATE` must exist** — verify automatically.
- **`ENUM` columns must be backed by a documented allowed-values list**, and every value written from PHP must be in it — verify automatically (an out-of-range ENUM write is truncated *silently*).
- Ship the schema as one importable `.sql` with **no `CREATE DATABASE` and no `USE`** (the host has no such privilege); the importer selects the database.

---

## 10) PHASE 7 — DEPLOYMENT CONSTRAINTS (the host is hostile — design for it)

InfinityFree free tier. These are verified facts:

| Constraint | Design consequence |
|---|---|
| **External MySQL connections are blocked** | The DB is reachable only from PHP on that account. There is no "connect from your laptop". |
| **No SSH** | No CLI on the server. Everything works over HTTP or phpMyAdmin. |
| **No `CREATE DATABASE` privilege** | The schema imports into an already-selected database. |
| **`sqlXXX.infinityfree.com` does not resolve from outside the network** | Use the alias that resolves *from inside*, and document that a mismatch is the #1 cause of "cannot connect to database". |
| **No Composer at runtime** | You cannot `composer require`. Any library must be **vendored as plain files** into the repo, or written by hand. (E.g. for XLSX import, a minimal `ZipArchive` + `SimpleXML` reader is often better than vendoring PhpSpreadsheet.) |
| **PHP extensions** | PHP ≥ 8.1 with `pdo_mysql`, `mbstring`, `curl`, `json`, `openssl`, `zip`. **`mbstring` is mandatory.** |
| **`.htaccess` is the only server config** | Rewrite for routing, `Options -Indexes`, security headers, and blocking `config/` and `tools/`. |
| **The web root may be a subfolder** | Compute the base path at runtime from `SCRIPT_NAME`; never hard-code `/`. |
| **No websockets, no long-running processes** | Use short polling (e.g. every 3–5 s) for chat/live updates. |
| **Cron via HTTP only** | Scheduled tasks = a `api/cron.php` endpoint hit by the host's cron job, guarded by a token. |

**Ship a web installer**: `tools/install.php?key=<one-time-key>` that imports the schema, creates the first owner account, writes an `.installed` marker so it cannot run twice, and must be deleted by the operator.

---

## 11) PHASE 8 — VERIFICATION MANDATE

### 11.1 Static checkers (write these first, wire into `verify.sh`)

| Checker | Enforces |
|---|---|
| `check_schema_columns.py` | Every column used in PHP `INSERT`/`UPDATE` exists in the schema. |
| `check_sql_params.py` | Placeholder count equals the number of bound values. |
| `check_enum_values.py` | Every literal written to an `ENUM` column is in the allowed list. |
| `check_fonts.py` | Bundled font files are real fonts (magic bytes), not HTML pages. |
| `check_served_secrets.py` | No server secret appears in any browser-reachable file. |
| `check_i18n.py` | No hard-coded user-visible Arabic string outside `lang/`. |
| `check_sql_injection.py` | No SQL built by concatenating variables. |

### 11.2 Test against a real database — mandatory

Mocks will not find the bugs that matter. **Stand up a real MariaDB/MySQL locally, import the schema, run the platform against it, and exercise the flows.**

- Import into a fresh DB → must import cleanly (no errno 150).
- Register → log in → hit a protected page and a protected API.
- **Log in, wait past the idle timeout, and confirm the session is still valid** — a PHP-vs-MySQL timezone mismatch silently breaks every session.
- Wrong password rejected, correct password accepted, pepper on/off both work.
- Submit an exam; confirm the correct answers were **not** present in any payload before submission.
- Upload a file, fetch it through the gateway as the owner (200) and as another user (403).
- Install a plugin from a ZIP → it appears in the menu and its settings page loads; uninstall → clean.
- Ask the AI assistant a question inside the indexed sources (answer + citations) and one outside (exactly `لا يوجد في المصادر`).
- Trigger a profanity violation 3 times → the account is banned for 30 days and a banned login notifies the admin.
- Check the audit log actually recorded each of the above.

Report the **actual** output. A test you claim to have run but did not is worse than no test.

### 11.3 Headless browser smoke test

Use headless Chromium (Playwright is available) to prove the UI works, not just the endpoints:
- Register → land on the dashboard → the layout is RTL → Cairo is the computed font.
- Log in as staff → the admin menu renders → open a course → edit → save → reload → the change persisted.
- Take a quiz end-to-end → the result screen shows the score.
- Send a chat message → it appears → profanity is masked.
- Assert **zero console errors** and **zero failed network requests** on those pages.

Capture screenshots into `docs/screenshots/` as evidence.

---

## 12) KNOWN TRAPS (these have already bitten this project — do not repeat them)

1. **`PASSWORD_PBKDF2` does not exist in PHP.** Only `PASSWORD_BCRYPT` / `PASSWORD_ARGON2I/ID`. Using it = `Fatal error: Undefined constant` on every login.
2. **A PHP-vs-MySQL timezone mismatch breaks every session.** PHP on `Africa/Cairo`, MySQL on UTC ⇒ stored expiry compares as "already expired". Fix: after connecting, `SET time_zone = '+02:00'` (PHP's current offset), and use one clock everywhere.
3. **FK ordering**: a table referencing `stickers`/`users`/`courses` must be created **after** its targets, or the import fails with errno 150.
4. **An `INSERT` with 6 placeholders but 5 values** throws only at runtime.
5. **An out-of-range `ENUM` write is silently truncated** — the row lands with an empty value and no visible error.
6. **A missing column** (`users.email`, `ai_messages.user_id` were both missing) — the schema and the code must agree, and a static checker must prove it.
7. **`session_regenerate_id(true)` on login** — without it, session fixation is possible.
8. **`is_uploaded_file()` + `finfo` for uploads** — `$_FILES['x']['name']` is attacker-controlled and the extension lies.
9. **`htmlspecialchars` without `ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'`** — breaks on Arabic and leaves `'` unescaped.
10. **Never `include`/`require` a path built from user input** — path traversal to remote code execution. Use an allow-list.
11. **A "font file" that is actually a GitHub 404 HTML page** passes a naive size check, then breaks rendering. Verify magic bytes (`00 01 00 00` for TTF) and the sfnt table count.
12. **A service worker that caches authenticated HTML/API responses** leaks one student's data to the next user on a shared device. **Only cache static assets**; mark private routes `no-store`.
13. **`$_SESSION` writes after output has started** — output buffering or session-write-early; otherwise headers are already sent and `session_start()` warns.
14. **`time()` vs `NOW()`** — mixing PHP time and DB time is the root of trap 2.
15. **Never put a secret in any served file.** A Gemini key in JS is extracted in seconds; the AI must be called from the server.
16. **Verify file *content*, not file size**, for every binary asset fetched from the network.

---

## 13) DELIVERABLES

```
/workspace/taleb-talta/
├─ admin-panel/
│  ├─ core/                     # autoloader, i18n, session, capability, audit, plugin engine
│  ├─ student/                  # student portal (pages)
│  ├─ admin/                    # staff area (pages)
│  ├─ api/                      # JSON API + cron.php
│  ├─ plugins/                  # <type>/<name>/…  (the plugin system)
│  ├─ lang/ar.php               # ALL user-visible strings (Egyptian)
│  ├─ themes/                   # 3+ themes
│  ├─ includes/                 # shared includes
│  ├─ config/config.php         # secrets here ONLY
│  ├─ storage/                  # uploads, outside web-servable paths
│  ├─ tools/install.php         # one-time web installer
│  └─ assets/                   # css/js/fonts/icons (self-hosted)
├─ database/schema.sql          # importable, no CREATE DATABASE / USE
├─ docs/
│  ├─ Taleb Talta specification.md
│  ├─ moodle-analysis.md        # Phase 1 output
│  ├─ feature-matrix.md         # Phase 1 output
│  ├─ lang-ar.md                # Phase 1 output
│  ├─ api-contract.md
│  ├─ DEPLOYMENT.md
│  ├─ PLUGIN-DEV.md             # how to write a plugin
│  └─ screenshots/
├─ tools/                       # the static checkers
└─ verify.sh
```

Plus:
- `docs/DEPLOYMENT.md` with a table of **real error messages → causes → fixes** (e.g. `getaddrinfo failed` → wrong host alias; `Unknown database` → wrong DB name; `Connection refused` → external DB access, which the host blocks; `Access denied` → wrong password; `Fatal error: Allowed memory size exhausted` → raise the limit / chunk the query).
- `docs/PLUGIN-DEV.md`: how to write, install, and debug a plugin (the developer-facing half of "إضافة المزايا").
- A working **deployable copy** of the platform (not just the diff) so it can be uploaded as-is.

---

## 14) HOW TO REPORT

Your final message, in this order:

1. **What Moodle taught you** — the 8 most important patterns you extracted, each with its Moodle file path.
2. **The Egyptian Arabic approach** — your tone rules, the glossary size, where the strings live, and 5 examples of before/after.
3. **What you built** — waves completed, file counts, LOC, table count, endpoint count, plugin count, theme count.
4. **Evidence** — the *actual* output of: the schema import, the login/authorised-access test, the session-timeout test, the exam-submission test, the file-gateway authorisation test, the plugin install/uninstall test, the AI inside/outside-sources test, the profanity-ban test, the headless-browser smoke test, and `verify.sh`.
5. **Known gaps** — be explicit about anything unfinished, stubbed, or unverified. Never claim a test you did not run.
6. **Deployment steps** — the exact order: files to upload, the one-time installer URL, the cron URL, and the post-install cleanup.

**Tone:** senior engineer. No filler, no "I'll now…". Specifics over adjectives. Show command output rather than describing it.

---

## 15) FIRST ACTION

**Do not write platform code yet.** First:

1. Unzip `moodle.zip`; produce an inventory of Moodle's plugin architecture and core subsystems with file paths (§4).
2. Read `Taleb Talta specification.md` in full.
3. Audit the **existing** Taleb Talta repo: what is implemented, what is broken, what is missing.
4. Extract the logo colours programmatically and report the measured hex values.
5. Produce `docs/moodle-analysis.md`, `docs/feature-matrix.md`, and `docs/lang-ar.md`.

**Deliver those three documents and wait for approval before Wave 0.**

Then proceed wave by wave, autonomously, reporting after each wave.
