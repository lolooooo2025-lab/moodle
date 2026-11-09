# Moodle 5.3 — Reverse-Engineering Analysis → Taleb Talta

> **Method.** This is *source-repository architecture analysis*, not binary reverse engineering.
> Per the REA skill's own routing rule ("Skip REA for ordinary source-repository architecture
> analysis"), the Moodle tree at `/home/user/moodle/public/` was read with normal repository
> tools (grep / read / AST-free inspection). Every claim below cites a real file path and line
> number from the shipped `5.3+ (Build: 20261021)` tree (`public/version.php`). REA's binary
> engines (Ghidra/Hopper/JADX) are not applicable to a PHP source tree and were not invoked.
>
> **Licensing (hard constraint).** Moodle is **GPLv3** (`COPYING.txt`). **No Moodle source code is
> copied into Taleb Talta.** We extract *architecture, invariants, and algorithms* and re-implement
> them as original code. Short quotations (≤15 lines) appear only in this analysis, marked as GPL
> Moodle code with their source path. "Inspired by Moodle" is recorded here and in the architecture
> doc. This is a clean-room-style reconstruction of *patterns*, not a derivative of the code.

Measured version facts:

| Fact | Value | Source |
|---|---|---|
| Release | `5.3+ (Build: 20261021)` | `public/version.php` |
| Core DB tables | **267** | `grep -c "<TABLE NAME=" public/lib/db/install.xml` |
| Core subsystems | **80** | `lib/components.json` → `subsystems` |
| Plugin types | **62** | `lib/plugins.json` → `standard` keys |
| Standard shipped plugins | **412** | `lib/plugins.json` → sum of `standard` |
| Core English strings | **2 351** in one file | `grep -c '^\$string' public/lang/en/moodle.php` |

---

## 1. The plugin / module architecture (the heart of "add any feature")

### 1.1 How a feature becomes a plugin

Moodle's entire extensibility rests on one convention: **a plugin is a directory in a known
location, described by a `version.php`, discovered by a central component manager, and wired into
core through a fixed set of `db/*.php` declaration files.** Nothing is registered by editing core.

Canonical layout (verified against `public/mod/lesson/`):

```
mod/lesson/
├─ version.php          # $plugin->version / requires / component / cron / maturity / dependencies
├─ lib.php              # core callbacks + navigation + capability helpers
├─ locallib.php         # domain classes (class lesson @1572, lesson_page @3899)
├─ db/
│  ├─ install.xml       # schema (8 tables: lesson, lesson_pages, lesson_answers, lesson_attempts,
│  │                    #           lesson_grades, lesson_timer, lesson_branch, lesson_overrides)
│  ├─ upgrade.php       # ordered version→version steps
│  ├─ access.php        # capability definitions ('mod/lesson:addinstance' => captype/contextlevel/archetypes)
│  ├─ events.php        # event observers
│  ├─ services.php      # external/web-service functions ($functions @29, 'ajax'=>true)
│  ├─ tasks.php         # scheduled tasks (classname + cron fields)
│  ├─ messages.php      # message providers
│  ├─ caches.php        # cache definitions
│  └─ log.php           # legacy log mapping
├─ classes/             # PSR-4-style autoloaded classes (mod_lesson\…)
├─ lang/en/lesson.php   # strings
├─ templates/  amd/  pix/  backup/
```

`version.php` (real, `public/mod/lesson/version.php`):

```php
$plugin->version   = 2026100500;     // YYYYMMDDXX
$plugin->requires  = 2026100200;     // minimum Moodle version
$plugin->component = 'mod_lesson';   // frankenstyle name
$plugin->cron      = 0;
```

**Invariant protected:** a plugin is *self-describing and self-contained*. Core never needs to know
a plugin exists ahead of time; it discovers it, reads its declarations, and wires it. If you omit
this, every new feature requires editing core → merge conflicts, no third-party ecosystem, no
safe install/uninstall. **Taleb Talta equivalent:** `plugins/<type>/<name>/` with `version.py` +
`manifest.json` + `db/install.sql` + `db/upgrade.py` + `db/access.py` + `db/events.py` +
`db/services.py` + `db/tasks.py` + `settings.py` + `lib.py` + `lang/ar.py` (§5.4 of the prompt).

### 1.2 Discovery and the plugin-type registry

- `core_component::get_plugin_types()` — `public/lib/classes/component.php:1231`. Returns the map
  `type → directory`. Sub-plugin support is declared at `component.php:73`
  (`$supportsubplugins = ['mod','editor','tool','local']`), and special-cased roots for `theme`
  (`:795`) and `local` (`:846`).
- The **canonical list of 62 plugin types** is data, not code: `lib/plugins.json` → `standard`.
  Types include `mod, block, auth, enrol, qtype, qbehaviour, theme, local, tool, report, filter,
  repository, format, editor, message, aiprovider, aiplacement, paygw, gradereport, dataformat, …`.
- `core\plugin_manager` (`public/lib/classes/plugin_manager.php`) is the runtime registry:
  - `get_plugin_types()` `:161`, `load_installed_plugins()` `:181`, `load_enabled_plugins()` `:241`,
    `load_present_plugins()` `:298` — the three states **present on disk / installed in DB / enabled**.
  - `are_dependencies_satisfied()` `:743`, `resolve_requirements()` `:822`,
    `missing_dependencies()` `:1211` — dependency graph resolution before install/upgrade.
  - `install_plugins()` `:1327`, `uninstall_plugin()` `:1525`, `can_uninstall_plugin()` `:1269`,
    `remove_plugin_folder()` `:1832`, `some_plugins_updatable()` `:1556`, `available_updates()` `:1613`.

**Invariant:** *present ≠ installed ≠ enabled* are three distinct states, and transitions between
them are explicit, audited operations. Omitting this conflation is what makes "disable a plugin
without losing its data" possible. **TT equivalent:** a `plugins` table with
`status ∈ {present, installed, enabled, disabled}` + `installed_version` vs `disk_version`.

### 1.3 Install / upgrade lifecycle

- Per-plugin metadata object: `core\plugininfo\base` (`public/lib/classes/plugininfo/base.php`):
  `load_disk_version()` `:281`, `load_db_version()` `:373`, `is_installed_and_upgraded()` `:219`,
  `get_status()` `:469`, `is_enabled()` `:513`, `load_settings()` `:626`,
  `uninstall_cleanup()` `:657`, `uninstall()` `:687`.
- The upgrade engine: `public/lib/upgradelib.php` — `upgrade_plugins()` `:672`,
  `upgrade_plugins_modules()` `:812`, `upgrade_plugins_blocks()` `:987`, `upgrade_noncore()` `:1963`,
  and the savepoint helper `upgrade_plugin_savepoint()` `:411` (each step records its version so a
  failed upgrade resumes rather than re-runs).
- Schema is declared in XML (`db/install.xml`) and applied by the XMLDB layer
  (`public/lib/xmldb/xmldb_*.php`), which is DB-engine-agnostic (MySQL/Postgres/MariaDB/MSSQL).
- The **admin plugin browser** is `public/admin/plugins.php` (params `uninstall/delete/installupdate/
  installupdatex/confirminstallupdate` at `:32–39`), and ZIP install is a *tool plugin itself*:
  `public/admin/tool/installaddon/classes/installer.php` + `installfromzip_form.php`.

**The lifecycle, in order:** discover → validate `version.php` + dependencies → apply
`db/install.xml` (schema) → register capabilities (`db/access.php`) → register observers
(`db/events.php`) → register tasks (`db/tasks.php`) → register services (`db/services.php`) →
install language strings → purge caches → bump the stored version → mark installed. Upgrade is the
same graph but runs `db/upgrade.php` steps keyed on the stored version.

**Invariant:** *install is a transaction with a savepoint per step; upgrade is monotonic and
resumable.* Omit it and a half-installed plugin corrupts the site. **TT equivalent:** an installer
that runs `db/install.sql` in a transaction, records each `db/upgrade.py` step in a
`plugin_upgrade_log`, and refuses to proceed on unmet dependencies.

### 1.4 How plugins extend core (the extension points)

| Extension point | Moodle mechanism (file:line) | TT equivalent |
|---|---|---|
| Navigation / menu | `core\navigation\global_navigation` `lib/classes/navigation/global_navigation.php:55`; plugin `lib.php` callbacks | `menu_items` table + plugin `lib.py::navigation()` |
| Settings node | `admin_get_root()` `lib/adminlib.php:772`; `plugininfo\base::load_settings()` `:626` | `plugin_settings` + settings tree |
| Events / observers | `core\event\manager::dispatch()` `lib/classes/event/manager.php:60`; `base::trigger()` `lib/classes/event/base.php:773` | event bus + `plugin_events` |
| Hooks (5.x, typed) | `core\hook\manager::dispatch()` `lib/classes/hook/manager.php:281` | typed hook dispatcher |
| Scheduled tasks | `core\task\manager` `lib/classes/task/manager.php:41`, `load_scheduled_tasks_for_component()` `:651` | `scheduled_tasks` + cron worker |
| Web services / API | `db/services.php` (`mod/quiz/db/services.php:29`), `lib/external/` | `db/services.py` → API router |
| Capabilities | `db/access.php`; `load_capability_def()` `lib/accesslib.php:2102` | `db/access.py` → capability catalogue |
| Question type | `question/type/<name>/` (17 types shipped) | `qtype` plugin |
| Course activity | `mod/<name>/` | `local`/`mod` plugin |
| Dashboard block | `blocks/<name>/` | `block` plugin |
| Theme | `theme/<name>/config.php` (`theme/boost/config.php:29`) | `theme` plugin (CSS variables) |
| Auth provider | `auth/<name>/` (10 shipped) | `auth` plugin |
| Enrolment | `enrol/<name>/`; `enrol_plugin` `lib/enrollib.php:1881`, `enrol_user()` `:2112` | `enrol` plugin |
| AI provider | `ai/provider/<name>/`; `core_ai\manager::process_action()` `ai/classes/manager.php:191` | `aiprovider` plugin (Gemini) |

**The "extend a core concept" pattern:** core defines an abstract base + a registry; a plugin
subclasses the base and drops itself in a scanned directory. Examples: `question/type/questiontypebase.php`
(base for all 17 question types), `enrol_plugin` (`enrollib.php:1881`), `core_ai\provider`
(`ai/provider/gemini/classes/provider.php:30` extends it). **TT equivalent:** every extensible
concept is an abstract base class + a directory scan + a registry table.

---

## 2. Core subsystem catalogue (80 subsystems; the ones that matter here)

Each row: what it is, the owning code, the tables it owns, and the invariant to copy.

### 2.1 Users & identity
- Code: `public/user/`, `public/lib/classes/privacy/`, custom profile fields via `customfield`.
- Tables (core `install.xml`): `user`, `user_info_data`, `user_info_field`, `user_preferences`,
  `user_private_key`, `cohort`, `cohort_members`, `groups`, `groups_members`.
- Invariant: **identity is separate from profile extensibility** — fixed registration columns +
  a custom-field EAV layer (`customfield/classes/field_controller.php:42`,
  `data_controller.php:35`, `handler.php:44`). Deletion vs anonymisation is handled by the privacy
  API, not by hard DELETE.

### 2.2 Authentication
- Code: `public/auth/` (10 providers: db, email, ldap, lti, manual, nologin, none, oauth2,
  shibboleth, webservice), `public/login/`, `public/lib/classes/authentication/`.
- Password hashing is delegated: `validate_internal_user_password()` `lib/moodlelib.php:4245` and
  `hash_internal_user_password()` `:4261` both call `\core\di::get(\core\authentication\password::class)`
  — i.e. **hashing is a swappable service, with pepper support** (`$pepperlength` param) and
  transparent re-hash on algorithm upgrade (`update_internal_user_password`).
- Invariant: **auth is a plugin chain, not an `if`**; password policy + reset + confirmation are
  separate flows; hashing is versioned and re-hashable.

### 2.3 Course structure
- Code: `public/course/`, `public/course/format/` (course formats are plugins), `public/enrol/`,
  `public/group/`, `public/completion/`.
- Tables: `course`, `course_categories`, `course_sections`, `course_modules`, `course_completion*`,
  `enrol`, `user_enrolments`, `context` (the polymorphic permission scope).
- Invariant: **a course is a container of sections → course-modules (activities)**, and every
  activity instance gets a `context` row so permissions can be scoped per-activity. Visibility and
  availability are separate from existence.

### 2.4 Content authoring — the Lesson module (the model for TT's lesson player)
- Code: `public/mod/lesson/locallib.php` — `class lesson` `:1572`, `class lesson_page` `:3899`,
  `lesson_add_page_form_base` `:1261`.
- Tables (8): `lesson`, `lesson_pages`, `lesson_answers`, `lesson_attempts`, `lesson_grades`,
  `lesson_timer`, `lesson_branch`, `lesson_overrides`.
- Invariant: **a lesson is an ordered graph of pages; each page has content + answers that branch
  to other pages; attempts and timers are separate tables.** This is exactly TT's "lesson player
  with content items (text/file/link/question) + completion + progress."

### 2.5 Quizzes & the question engine
- Code: `public/mod/quiz/classes/quiz_attempt.php:54` (`class quiz_attempt`),
  `public/question/engine/` (`questionusage.php`, `questionattempt.php`, `states.php`),
  `public/question/type/` (17 types: multichoice, truefalse, shortanswer, match, numerical, essay,
  ordering, ddwtos, ddimageortext, ddmarker, gapselect, calculated*, multianswer, randomsamatch, …).
- Tables: `quiz`, `quiz_slots`, `quiz_sections`, `quiz_attempts`, `quiz_grades`, `quiz_feedback`,
  `quiz_overrides`, `question`, `question_versions`, `question_bank_entries`, `question_attempts`,
  `question_attempt_steps`, `question_attempt_step_data`.
- **The critical invariant:** the question engine is a *state machine* (`state.php`) that stores
  each step server-side; **correct answers and grading live on the server and are never shipped to
  the browser before submission.** TT must grade objective questions server-side and only reveal
  the key after submit (prompt §6 Wave 2).

### 2.6 Communication
- Forums `public/mod/forum/`, messaging `public/message/classes/api.php:33`
  (`send_message_to_conversation()` `:1542`), chat `public/mod/chat/`, comments `public/comment/`.
- Tables: `forum`, `forum_discussions`, `forum_posts`, `message`, `message_conversations`,
  `message_conversation_members`, `message_contacts`, `chat`, `chat_messages`, `comments`.
- Invariant: **read-state, blocking, and moderation are first-class tables**, not afterthoughts.

### 2.7 Grading
- Code: `public/grade/`, `public/lib/gradelib.php` (`grade_update()` `:64`),
  `public/grade/grading/` (advanced grading methods are plugins), `public/grade/report/`.
- Tables: `grade_items`, `grade_grades`, `grade_categories`, `grade_outcomes`, `grade_letters`,
  `grading_areas`, `grading_definitions`, `grading_instances`.
- Invariant: **a gradebook is a tree of grade items + categories with aggregation**, decoupled from
  the activity that produced the grade (`grade_update($source,…)` is the universal write API).

### 2.8 Files & media
- Code: `public/lib/filestorage/file_storage.php:46` (`class file_storage`),
  `send_stored_file()` `lib/filelib.php:2674`, gateway `public/pluginfile.php`, repositories
  `public/repository/` (plugin type).
- Tables: `files`, `files_reference`.
- **Invariant (the security crux):** files are **content-addressed on disk** and served only through
  an *authorised gateway* (`pluginfile.php`) that checks context + capability before streaming.
  There is no public URL to an uploaded file. TT copies this as its file gateway (prompt §7.7).

### 2.9 Calendar, notifications, search, analytics
- Calendar `public/calendar/` (`event` table); notifications `core\notification` +
  `message` providers; search `public/search/` (search areas are plugins); analytics
  `public/analytics/` (prediction models are plugins); report builder `public/reportbuilder/`.
- Invariant: **notifications have per-user read-state and per-provider preferences**; search is an
  index fed by pluggable "areas"; reports are declarative (reportbuilder) not hand-written SQL.

### 2.10 Administration & customization
- Admin tree: `admin_get_root()` `lib/adminlib.php:772`; settings pages `public/admin/settings/*.php`
  (ai, appearance, courses, grades, language, location, login, messaging, payment, plugins, …).
- Themes: `theme/boost/config.php:29` (`$THEME->name`, `parents`, `scss`, `layouts`) — a theme is a
  config + SCSS + layouts, with parent/child inheritance.
- Custom fields: `public/customfield/` (handler/field_controller/data_controller) attached to
  courses, users, cohorts, categories.
- Blocks/dashboards: `public/blocks/` + `public/my/` (the per-user dashboard).
- Invariant: **the admin panel is a tree of settings pages + tool pages + a plugin browser**, and
  *every* customizable surface (theme, fields, blocks, menus, language) is data-driven.

### 2.11 AI subsystem (directly relevant to the spec's Gemini agent)
- Code: `public/ai/classes/manager.php:30` (`process_action()` `:191`), providers
  `public/ai/provider/` (anthropic, awsbedrock, azureai, deepseek, **gemini**, ollama, openai),
  placements `public/ai/placement/`.
- `ai/provider/gemini/classes/provider.php:30` (`class provider extends \core_ai\provider`) with
  actions `generate_text`, `summarise_text`, `explain_text`, `generate_image`.
- Invariant: **AI is a provider/placement split** — the *provider* talks to the model (server-side,
  key never leaves the server), the *placement* decides where in the UI it appears. TT's Gemini RAG
  assistant copies this split and adds a retrieval layer over the approved knowledge base.

---

## 3. Admin-panel architecture (what makes it feel "complete")

Moodle's admin area (`public/admin/`) is three things layered:

1. **A settings tree** — `admin_get_root()` (`adminlib.php:772`) builds a category → page → setting
   graph. Each setting is an object (`admin_setting_configtext`, `_configselect`, `_configcheckbox`,
   …) that knows how to render, validate, and persist itself to `config` / `config_plugins`.
2. **Tool pages** — `admin/tool/<name>/` are full pages (installaddon, health, scheduled tasks,
   purge caches, …). They are themselves plugins, so the admin area is extensible by the same
   mechanism as everything else.
3. **The plugin browser** — `admin/plugins.php` lists *present/installed/enabled* plugins with
   install/upgrade/uninstall/disable actions, dependency warnings, and version comparisons.

**What makes it feel complete vs thin:** (a) every setting is persisted + validated + audited;
(b) the plugin browser shows *state and available updates*, not just a list; (c) reports and logs
are reachable from the same tree; (d) destructive actions are confirmed + capability-gated.
**TT equivalent:** a settings tree backed by `site_settings` + `plugin_settings`, a plugin manager
page, a reports section, and an audit log — all capability-gated and `sesskey`-protected.

---

## 4. Pattern → invariant → Taleb Talta equivalent (the transfer table)

| # | Moodle pattern (file:line) | Invariant it protects | Taleb Talta equivalent |
|---|---|---|---|
| 1 | Self-describing plugin dir + `version.php` (`mod/lesson/version.php`) | Features added without editing core | `plugins/<type>/<name>/` + `version.py`/`manifest.json` |
| 2 | present/installed/enabled states (`plugin_manager.php:181/241/298`) | Disable ≠ lose data | `plugins.status` + version columns |
| 3 | Savepoint-per-step upgrade (`upgradelib.php:411`) | Resumable, monotonic upgrades | `plugin_upgrade_log` + ordered `db/upgrade.py` |
| 4 | Capability resolution ALLOW/PREVENT/PROHIBIT (`accesslib.php:115-119,788`) | AuthZ is data, not role `if`s | `tt_can()` + `TT_CAPABILITIES` + role overrides |
| 5 | `require_sesskey()` (`sessionlib.php:83`) | CSRF on every mutating request | `sesskey` on all writes + Origin check |
| 6 | `require_login()` (`moodlelib.php:2259`) | One gate for authN+authZ+context | single `require_login()` middleware |
| 7 | Swappable, peppered, re-hashable password service (`moodlelib.php:4245-4261`) | Hash agility + pepper rotation | PBKDF2 service + pepper + transparent re-hash |
| 8 | Content-addressed files + authorised gateway (`file_storage.php:46`, `pluginfile.php`) | No public URL to private files | file gateway with capability + ownership check |
| 9 | Server-side question state machine (`question/engine/states.php`) | Answers never leak pre-submit | server-only grading + post-submit reveal |
| 10 | Event bus + typed hooks (`event/manager.php:60`, `hook/manager.php:281`) | Decoupled side-effects, auditable | event bus + `plugin_events` |
| 11 | Universal grade write API (`gradelib.php:64`) | Gradebook decoupled from activities | `grades` + `grade_update()` |
| 12 | Data-driven theme/fields/blocks/menus (`theme/boost/config.php`, `customfield/`) | Customization without code | CSS-variable themes + custom-field EAV + block/menu tables |
| 13 | AI provider/placement split (`ai/classes/manager.php:191`) | Key stays server-side; UI decoupled | Gemini provider + RAG retrieval + placement |
| 14 | String manager + per-component lang files (`string_manager_standard.php`, `lang/en/moodle.php`) | No hard-coded UI strings; i18n-ready | `lang/ar.py` + `t()` + hard-coded-string checker |

---

## 5. "We deliberately deviate" (copy the invariants, not the scale)

Moodle serves thousands of institutions and millions of users across many DB engines and auth
backends. Taleb Talta serves **one school brand**. We copy the *invariants* and drop the
*generality* we don't need:

| Moodle generality | TT decision | Why |
|---|---|---|
| 62 plugin types, sub-plugins, XMLDB across 4 DB engines | ~10 plugin types, one DB engine (PostgreSQL), SQL migrations | One engine removes the XMLDB abstraction tax |
| Multi-tenant `context` tree (system/category/course/module/block/user) | Single-tenant contexts: system / division / course / lesson / exam | One school; fewer context levels, same resolution order |
| MNet, LTI, Shibboleth, LDAP, OAuth2, 10 auth providers | Phone+password auth now; `auth` plugin type reserved for SSO later | Spec §9 registration is phone+password+guardian+division |
| SCORM, H5P, workshop, full forum rating/subscription matrix | Lesson player + quiz + forum-lite + chat | Match the 11-item spec, not all of Moodle |
| Full gradebook aggregation tree + scales + outcomes | Per-course marks + totals + ranking + CSV/Excel export | Spec §3 needs totals/ranking, not weighted categories |
| **PHP + MySQL + no-framework + InfinityFree (prompt §5.1)** | **See §6 — the user overrode this for 300K+ scale** | The user explicitly asked for 300K+ users and "not PHP only" |

**Explicit deviation from the prompt's hosting target.** The prompt targets InfinityFree free tier
(~1 000 students, PHP-only, no Composer, no build step). The **user's direct instruction supersedes
this**: *"build in python with php or what you feel the best with (not php only) … strong enough to
handle 300K+ users or more; like moodle."* 300K+ concurrent-capable users is **not** achievable on
InfinityFree free tier. We therefore target a real scalable deployment (§6) while keeping the
Moodle-grade invariants, the Egyptian-Arabic-first product, and the plugin architecture.

---

## 6. Recommended Taleb Talta stack for 300K+ users

> Decision rationale, not yet approved. Presented for the Wave-0 gate.

| Layer | Choice | Why it scales to 300K+ |
|---|---|---|
| Language / framework | **Python 3.11 + FastAPI** (async) | Async I/O handles tens of thousands of concurrent connections per node; horizontal scale behind a load balancer |
| Database | **PostgreSQL 15+** | Proven at this scale; strong concurrency (MVCC), partial/covering indexes, partitioning for `messages`/`audit_log`; runnable locally via `pgserver` for real-DB tests |
| Cache / sessions / rate-limit | **Redis** | Server-side sessions, `sesskey`, rate-limit counters, hot-path caching (courses, menus, settings) |
| Background jobs | **arq / Celery worker** | Broadcasts to 300K, digests, AI indexing, cleanup, backup — off the request path |
| Rendering | **Jinja2 server templates + vanilla ES-module JS** | Keeps the "no build step" spirit, tight CSP, RTL-first; no bundler |
| Real-time | **Short polling (3–5s)** now; WebSocket/SSE later | Matches the prompt's no-websocket constraint on cheap hosts; upgrade path open |
| Files | **Local disk / S3-compatible object store + authorised gateway** | Content-addressed, never public; CDN in front for static |
| AI | **Gemini provider (server-side) + pgvector retrieval** | Key never leaves server; RAG over approved knowledge base |
| Deploy | **Docker + nginx + uvicorn/gunicorn workers** | Reproducible, horizontally scalable; a far cry from shared hosting |

**What we keep from the prompt regardless of stack:** Egyptian colloquial Arabic everywhere, RTL,
self-hosted Cairo font, no CDN, capability-based authZ, `sesskey` CSRF, PBKDF2+pepper passwords,
server-side sessions with idle+absolute timeout, audit log, authorised file gateway, server-side
exam grading, plugin architecture, admin-configurable everything, and the static checkers +
real-DB verification mandate.

**Environment readiness already verified in this sandbox:** Python 3.11, `pgserver` (real
PostgreSQL) installed, Pillow installed (logo colours extracted), gcc/make present, Node 22 present.
PHP and MySQL are *not* installed and `apt` is unavailable, which independently confirms Python +
PostgreSQL is the pragmatic, testable choice here.

---

## 7. Security invariants extracted (the point of the exercise)

1. **AuthZ is capability resolution, not role checks.** `has_capability()` `accesslib.php:432`,
   `has_capability_in_accessdata()` `:788` with `CAP_ALLOW=1 / CAP_PREVENT=-1 / CAP_PROHIBIT=-1000`
   (`:115-119`); any PROHIBIT wins (`:837`). → TT `tt_can()` with the same precedence.
2. **One login gate.** `require_login()` `moodlelib.php:2259` enforces authN + enrolment + context +
   sesskey in one place. → TT middleware.
3. **CSRF token on every write.** `sesskey()` `sessionlib.php:36`, `require_sesskey()` `:83`.
4. **Password hashing is a versioned, peppered, re-hashable service.** `moodlelib.php:4245-4261`.
   → TT PBKDF2-HMAC-SHA256 (310k iters, 256-bit salt, server pepper), `hash_equals`, transparent
   re-hash, tolerate pepper enabled later.
5. **Files never have public URLs.** `file_storage.php:46` + `pluginfile.php` gateway +
   `send_stored_file()` `filelib.php:2674`. → TT authorised gateway, `finfo` MIME, allow-list,
   octet-stream for non-images, never `include` an upload.
6. **Exam answers stay server-side until submit.** Question engine state machine
   (`question/engine/states.php`). → TT grades on server, reveals key only post-submit.
7. **Everything is audited and event-driven.** `event/base.php:773` `trigger()` →
   `event/manager.php:60` `dispatch()`. → TT append-only `audit_log` + event bus.
8. **No secrets in served files; AI key server-side.** AI provider split
   (`ai/classes/manager.php:191`). → TT secret-scanner checker + server-only Gemini calls.

---

*Inspired by Moodle (GPLv3). No Moodle source code is reproduced in Taleb Talta; only architectural
patterns and invariants are re-implemented as original code. Quotations above are ≤15 lines and
marked with their GPL source path.*
