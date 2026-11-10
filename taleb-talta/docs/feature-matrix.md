# Feature Matrix — Moodle → Taleb Talta

Status legend: **exists** = present and tested · **partial** = present with a named gap ·
**to build** = not yet built · **out of scope** = deliberately excluded (reason given).
Priority: P0 (must), P1 (should), P2 (nice).
Wave refers to the prompt's §6 build waves.

> **Repo-audit note.** The prompt (§1.2) describes a pre-existing partial PHP repo that is **not
> present** in this environment (only the Moodle source + logo/spec/prompt were attached). The
> platform was therefore built fresh in Python/FastAPI/Postgres (user-approved). **Waves 0–5
> are now built and verified** (`verify.sh` → ALL PASSED:
> 43 + 32 + 35 + 98 + 128 + 153 + 54 + 22 = 565 checks). Rows below marked **exists** are implemented and tested;
> **partial** notes what remains. See `docs/wave5-report.md` / `docs/wave5-verify.log` for evidence. Dark mode was dropped by user directive — all themes are light.

## Core platform

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| Plugin architecture | `lib/classes/plugin_manager.php`, `component.php` | `plugins/<type>/<name>/` engine + installer | exists | P0 | 0 |
| Capability authZ | `lib/accesslib.php:432,788` | `tt_can()` + `TT_CAPABILITIES` | exists | P0 | 0 |
| Sessions + CSRF | `lib/sessionlib.php:36,83`, `lib/classes/session/` | server sessions + `sesskey` | exists | P0 | 0 |
| AuthN (login/register/reset) | `auth/`, `login/` | phone+password+guardian+division | exists | P0 | 0 |
| Password hashing service | `lib/moodlelib.php:4245` | PBKDF2+pepper service | exists | P0 | 0 |
| i18n / string manager | `lib/classes/string_manager_standard.php` | `lang/ar.py` + `t()` | exists | P0 | 0 |
| Layout / navigation | `lib/classes/navigation/global_navigation.php:55` | RTL layout + role-aware menu | exists | P0 | 0 |
| Audit log | `lib/classes/event/` | append-only `audit_log` | exists | P0 | 0 |
| Admin settings tree | `lib/adminlib.php:772`, `admin/settings/` | typed `site_settings` + general/branding/security tree | exists | P0 | 4 |
| Admin panel consistency | `admin/`, staff pages | shared subnav + role-aware dashboard; W5 purchases/broadcasts/campaigns/live implemented | exists | P0 | 4/5 |
| Plugin browser | `admin/plugins.php`, `admin/tool/installaddon/` | lifecycle manager + typed settings; vetted on-disk packages | exists (ZIP upload deferred) | P0 | 4 |
| Backups / restore | `admin/tool/backup`, `restore/` | real pg_dump + uploads archive, checksum, retention | partial (no restore path yet) | P1 | 4 |

## Users, identity, access

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| User profiles | `user/` | profile (name/photo/title/badge editable) | exists | P0 | 0 |
| Custom profile fields | `customfield/` | user/course custom-field builder + report filters | exists | P1 | 4 |
| Cohorts / groups | `cohort/`, `group/` | divisions (شعبة) + cohorts | exists | P0 | 1 |
| Enrolment | `enrol/`, `lib/enrollib.php:1881` | enrol by division + manual paid unlock (confirmed purchase only) | exists | P0 | 1/5 |
| Suspension / ban | `user/`, auth | scoped 30-day chat+evals ban + admin login alert | exists | P0 | 3 |
| Privacy / GDPR | `lib/classes/privacy/` | anonymise vs delete | to build | P2 | later |
| 2FA / SSO | `auth/oauth2`, `admin/tool/mfa` | reserved `auth` plugin type | out of scope (v1) | P2 | later |

## Courses & content

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| Course categories | `course/` | course categories + icons | exists | P0 | 1 |
| Courses CRUD + soft delete | `course/` | courses + trashcan (owner-only purge) | exists | P0 | 1 |
| Sections | `course/format/` | course sections | exists | P0 | 1 |
| Lesson player | `mod/lesson/locallib.php:1572,3899` | pages: text/file/link/question + progress | exists | P0 | 1 |
| Completion tracking | `lib/completionlib.php:238` | lesson progress + completion | exists | P0 | 1 |
| Shared library + approval | `repository/`, `files/` | library + moderator approval workflow | exists | P0 | 1 |
| Private student space | `files/` (private file area) | per-student area + IndexedDB offline | exists (offline browse=W later) | P1 | 1 |
| Availability dates | `availability/date` | course/lesson available-from/to | exists | P1 | 1 |
| SCORM / H5P / book | `mod/scorm`, `h5p/`, `mod/book` | — | out of scope (spec doesn't need) | P2 | — |
| Assignment / workshop | `mod/assign`, `mod/workshop` | — | out of scope (v1) | P2 | — |

## Exams & grading

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| Question bank | `question/`, `question/type/` | MCQ single/multi, T/F, short, match, numeric | exists (6 types) | P0 | 2 |
| Question editor | `question/type/edit_question_form.php` | admin question editor | exists | P0 | 2 |
| Quiz attempts | `mod/quiz/classes/quiz_attempt.php:54` | timed attempts, 1..N, server grading | exists | P0 | 2 |
| Server-side grading | `question/engine/states.php` | answers never pre-leaked | exists | P0 | 2 |
| Gradebook | `grade/`, `lib/gradelib.php:64` | per-course marks/totals/ranking + export | exists (+CSV) | P0 | 2 |
| Result discussion | `mod/forum/` | per-question discussion + deep-link chip | exists | P1 | 2 |
| Drag-drop / calculated qtypes | `question/type/dd*`, `calculated*` | — | out of scope (v1) | P2 | — |
| Competencies / badges | `competency/`, `badges/` | editable profile badge only | partial (no competency framework) | P2 | later |

## Communication

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| Forum | `mod/forum/` | threads/posts/replies/subscriptions/lock + moderation | exists | P0 | 3 |
| 1:1 messages | `message/classes/api.php:1542` | contacts, read/unread, block, report | exists | P0 | 3 |
| Chat (1:1/group/division) | `mod/chat/` | channels + private attachments + stickers + cursor polling | exists | P0 | 3 |
| Stickers + approval | — | student-made stickers, moderator approval | exists | P1 | 3 |
| Profanity filter + escalation | `filter/` | editable dictionary, mask+warn, 3rd → scoped 30-day ban | exists | P0 | 3 |
| Moderation queue | `report/`, `tool/` | reported content → approve/remove/warn/ban, audited | exists | P0 | 3 |
| Ratings / subscriptions | `rating/`, forum subs | forum subscriptions + unread markers | exists (subs; no ratings) | P2 | 3 |

## Money, broadcasts, live

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| Paid enrolment | `enrol/paypal`, `paygw/` | manual settlement + admin confirm/reject/cancel, server `PAID_CONTENT_LOCKED` | exists | P0 | 5 |
| Per-lesson purchase | `enrol/` | pay-per-lesson unlock in free courses; mixed pricing rejected | exists | P1 | 5 |
| Live streaming | `mod/bigbluebuttonbn` (concept) | stream metadata + hls.js player + live chat + owner-only encrypted key | partial (real HLS ingest/playback unproven) | P1 | 5 |
| Targeted notifications | `message/`, `core/notification` | all/role/division/course/individual + per-user read-state + history | exists | P0 | 5 |
| Friday campaign | — | Friday 09:00 Cairo, one per week, cron publish + archive | exists | P1 | 5 |
| Web Push | `message/output/popup` | VAPID subscriptions, bounded fan-out, SW push/click | partial (stub-tested; external delivery unproven) | P1 | 5 |
| Payment gateways | `paygw/` | — | out of scope (spec: no gateways) | — | — |

## AI, calendar, customization

| Moodle feature area | Moodle source | Taleb Talta equivalent | Status | Priority | Wave |
|---|---|---|---|---|---|
| AI provider/placement | `ai/classes/manager.php:191`, `ai/provider/gemini/` | Gemini RAG assistant (Egyptian, citations) | to build | P0 | 6 |
| AI knowledge base | `contentbank/` (concept) | admin-managed KB + seed from courses | to build | P0 | 6 |
| Calendar / agenda | `calendar/` | calendar + upcoming deadlines | to build | P1 | 6 |
| Themes | `theme/boost/config.php:29` | 3 light CSS-variable themes + brand presets + role override | exists | P0 | 4 |
| Dashboard blocks | `blocks/`, `my/` | per-role defaults + per-user order/visibility builder | exists | P1 | 4 |
| Menu builder | `lib/classes/navigation/` | admin-managed internal links (role/icon/order) | exists | P1 | 4 |
| Reports / exports | `reportbuilder/`, `dataformat/` | enrolments/activity/grades/usage/audit + safe CSV/XLSX | exists | P0 | 4 |
| Scheduled tasks | `lib/classes/task/manager.php:41` | cron parser + locks/history + worker (digests/cleanup/backup/campaign/push) | exists | P0 | 4/5 |
| Global search | `search/` | search over courses/library | to build | P2 | 6 |
| Analytics models | `analytics/` | usage/activity reports (no prediction models) | exists (basic) | P2 | 4 |

## Deliberately out of scope (with reason)

- **Multi-tenancy / MNet / LTI / Shibboleth / LDAP** — one school brand; not needed.
- **SCORM, H5P, workshop, full assignment grading** — not in the 11-item spec.
- **Payment gateways** — spec §5 explicitly says manual settlement via support, no gateways.
- **Advanced question types (drag-drop, calculated, gap-select)** — v1 ships the 6 objective types the spec needs.
- **Full weighted gradebook / outcomes / scales** — spec needs totals + ranking + export, not aggregation trees.
- **Mobile push (APNs/FCM)** — web push / in-app notifications first; native push is a later integration.
- **Plugin ZIP upload** — deferred: arbitrary owner-uploaded code is a remote-code-execution risk; v1 installs vetted on-disk packages only.
- **Backup restore UI** — not yet built; Wave 4 ships create/download/delete/retention and verifies dumps with `pg_restore --list`.
