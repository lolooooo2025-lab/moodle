# Wave 5 report — Paid content, notifications, Friday campaign, live streams

Status: **implemented — it runs.** Verified against real PostgreSQL and headless
Chromium. `bash verify.sh` exits 0. Full gate output: `docs/wave5-verify.log`.

## 1. What was built (prompt §6, Wave 5)

- **Manual paid enrolment**: course-level and per-lesson pricing in integer EGP
  piastres; mixed course+lesson pricing rejected. Students request a manual
  transfer with a reference; owner/admin confirm/reject from a paginated queue.
  Only a **confirmed** purchase unlocks content. Rejection requires a reason;
  students can cancel their own pending request. No payment gateway is involved.
- **Server-enforced locks**: lesson player, lesson items/files, completion,
  question checks, exam list/detail/start, and question discussions return
  `403` with `data.code = PAID_CONTENT_LOCKED` when paid access is missing.
  Owner/admin/assigned-teacher bypass remains capability-based. The shared
  library is independent of course purchases.
- **Targeted notifications**: all / role / division / course / individual
  audiences, per-user read state, mark-one/mark-all, unread badge, broadcast
  history. Campaign unread rows are counted once (regression-tested).
- **Friday campaign**: one campaign per week, Friday 09:00 Africa/Cairo,
  scheduled/published states, cron publication, public archive and per-user
  read state. Duplicate week → `409`; early manual publish → `409`.
- **Web Push (best-effort)**: VAPID key derived from the persisted secret,
  subscription validation (P-256 point, auth length, exact provider hosts,
  HTTPS/443, no control characters), 5-device cap, shared-device endpoint
  transfer, bounded fan-out (10 recipients × 5 devices, 5s provider timeout,
  redirects disabled), expiry removal after 404/410 or 10 failures. In-app
  notifications never depend on push success. Service worker handles `push` and
  notification clicks; manifest is installable.
- **Live streams**: scheduled/live/ended/cancelled lifecycle, all/course/division
  audiences, HTTPS playback URL validation, vendored `hls.js`, live chat channel
  with the same audience ACL. Publish key + ingest URL are Fernet-encrypted at
  rest and **owner-only** (reveal/rotate audited); admins manage metadata but
  cannot see credentials. Managers can edit a scheduled stream without wiping
  its playback URL.
- **Migration/seed**: `database/migrations/005_wave5.sql` +
  `tools/migrate_wave5.py` (idempotent, single transaction). The first-draft
  migration had type/constraint/FK/index drift vs the ORM; it is now repaired
  in place and `tools/check_live_schema.py` compares the running database to the
  ORM contract (types, nullability, PK/FK/unique/CHECK/index definitions).
  `database/schema.sql` is regenerated and matches the models.

## 2. Evidence (actual output)

```
check_i18n / check_served_secrets / check_fonts / check_enum_values /
check_sql_injection / check_schema_columns .... all PASS (61 tables, 469 columns)
migrate_wave4.py .............................. PASS (62 live tables)
migrate_wave5.py .............................. OK (idempotent)
migrate_wave3.py .............................. PASS (62 live tables)
check_live_schema.py .......................... PASS (61 ORM tables match live PostgreSQL)

verify_wave0.py  == RESULT: 43/43 checks passed ==
verify_wave1.py  == RESULT: 32/32 checks passed ==
verify_wave2.py  == RESULT: 35/35 checks passed ==
verify_wave3.py  == RESULT: 98/98 checks passed ==
verify_wave4.py  == RESULT: 128/128 checks passed ==
verify_wave5.py  == RESULT: 153/153 checks passed ==
browser_smoke.py == BROWSER SMOKE: 54/54 passed ==
browser_wave5.py == BROWSER WAVE5: 22/22 passed ==
verify.sh        → VERIFY: ALL PASSED   (565 checks total)
```

Selected Wave-5 assertions (from `verify_wave5.py`):
```
[PASS] self-enrol into paid course locked / paid lock on lesson, file, exam, question discussion
[PASS] purchase request created / pending request still locks / duplicate rejected
[PASS] admin confirms purchase / confirmed unlocks lesson, file, exam, sibling lesson
[PASS] other student still locked / double confirm rejected / reject requires reason
[PASS] per-lesson request created / purchased lesson unlocks / sibling remains locked
[PASS] mixed course+lesson pricing rejected / whitespace reference rejected
[PASS] campaign counted once in unread total / campaign read state isolated
[PASS] duplicate week rejected / early manual publish rejected / publish idempotent
[PASS] manager can edit scheduled playback URL / stream edit preserves playback URL
[PASS] publish key encrypted at rest / owner reveals exact key / admin cannot reveal key
[PASS] division stream hidden from other division / paid-course stream locked for non-buyer
[PASS] invalid push curve point rejected / broad googleapis subdomain rejected
[PASS] shared endpoint transfers to current account / five devices allowed / sixth rejected
[PASS] push provider timeout bounded / redirects disabled / partial device failure still delivers sibling
[PASS] expired push subscription removed / failed push does not remove in-app notification
```

Browser (from `browser_wave5.py`): owner pricing UI → admin live table/key/ingest
reveal → broadcast history → campaign schedule/publish → student locked paid
course → purchase request → admin confirmation queue → targeted/purchase
notifications → mark-read → Friday archive body → live list/player metadata →
scheduled player hides video → vendored hls.js → confirmed purchase unlocks
lesson UI. **Zero console errors / zero failed requests.** Screenshots:
`docs/screenshots/35-course-pricing.png` through `44-unlocked-lesson.png`.

## 3. Build size (cumulative, Wave 0–5)

| Metric | Count |
|---|---|
| Python files (app/) | 64 |
| Python LOC (app/) | 10,260 |
| Templates | 49 |
| JS files (static/js, incl. vendored hls.js) | 39 |
| Arabic strings (`lang/ar.py`) | 1,144 |
| API paths / operations | 197 / 218 |
| ORM DB tables / columns | 61 / 469 |
| Live DB tables | 62 (incl. plugin-managed `backup_records`) |
| Light base themes | 3 (+ brand presets) |

## 4. Security/UX notes

- Secrets are loaded from the environment or a private owner-only env file;
  no usable owner-password fallback is shipped in source. Clean delivery archives
  exclude the private file, storage and database data.
- Every write is capability-gated, CSRF-checked and audited. Purchase review,
  stream credentials, pricing and broadcast surfaces are separated by capability.
- Pricing/purchase/stream mutations take row locks; pending-purchase uniqueness
  is enforced by partial unique indexes; enrolment insertion is conflict-safe.
- Push endpoints are allowlisted by exact provider host (no broad
  `googleapis.com` wildcard), redirects are disabled, and device count/timeouts
  are bounded so a cron lease cannot be exhausted by one user.
- Live `can_chat` respects `chat/send`; ended/cancelled streams close chat and
  hide playback. Ingest/key never appear in public or admin-list payloads.
- Light-only RTL Cairo UI; all copy via `t()`; no inline styles; service worker
  cache bumped to `tt-static-v8`, uses network-first static refresh with an
  offline fallback, and still caches static assets only.
- Preview login now verifies `/api/auth/me` before showing success. If an
  embedded browser rejects the session cookie, the UI shows an explicit error
  and an “open standalone window” action instead of bouncing silently. The
  cross-site regression is recorded in `docs/preview-login-verify.log` (10/10).

## 5. Known gaps (honest)

- **External Web Push delivery is not proven**: fan-out, validation, expiry and
  failure handling are exercised with a local provider stub. Real Mozilla/FCM/
  Apple delivery needs a deployed HTTPS origin and browser subscription.
- **Real HLS ingest/playback is not proven**: the app verifies metadata, ACLs,
  encrypted credentials, player payloads and vendored hls.js. It does not run an
  encoder/CDN; `ffmpeg` is unavailable in this sandbox.
- Historical exam attempts are not re-gated if access changes later; new
  attempts/discussions are gated.
- Backups still have no restore path; plugin ZIP upload remains deferred.
- Admin purchase queue is paginated (100/page); broadcast/campaign/live lists
  are capped at 100 rows with no cursor pagination yet.
- Embedded browsers that reject all third-party/partitioned cookie storage
  require the explicit standalone-window action; first-party login is verified.
- The live DB contains one plugin-managed table outside the ORM contract;
  `check_live_schema.py` validates all 61 ORM tables and ignores plugin tables.

## 6. Next

Wave 6 (per prompt): Gemini RAG assistant with admin knowledge base, calendar /
upcoming deadlines, and global search over courses/library.
