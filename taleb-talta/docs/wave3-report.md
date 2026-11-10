# Wave 3 report — Professional communication

Status: **implemented — it runs.** Verified against real PostgreSQL and headless
Chromium. `bash verify.sh` exits 0. Full gate output: `docs/wave3-verify.log`.

## 1. What was built (prompt §6, Wave 3)

- **Forum**: general and course-scoped threads, nested replies, subscriptions,
  unread markers, explicit read state, staff lock/unlock, and question-thread
  deep links from exam review. Question threads require a submitted/graded
  attempt (or grading staff); course threads require course access.
- **Messages**: 1:1 conversations, exact-phone contact discovery, contact list,
  read/unread counts, read receipts, two-way blocking, reporting.
- **Chat channels**: private 1:1, group (creator-managed members, max 50), and
  automatic division channels. Cursor-based AJAX polling (`after_id`), no
  WebSockets required. Division membership is derived server-side.
- **Attachments**: images, video, PDF/text/OOXML study resources. Bounded
  upload reads, magic-byte + image/OOXML validation, SHA-256, opaque private
  storage keys, parent-message download ACLs, `private, no-store`, `nosniff`,
  video Range support, and a 100 MiB per-user upload quota (25 MiB per file).
- **Stickers**: student-submitted images stay private until moderator approval;
  approved stickers are sendable; rejection requires a reason.
- **Profanity policy**: editable DB dictionary seeded from
  `database/profanity.json`. Arabic normalisation (variants/diacritics/tatweel/
  control chars) with original casing/diacritics preserved outside masked spans.
  One strike per submission, atomic PostgreSQL upsert. 1st/2nd warning, 3rd →
  **30-day scoped ban covering chat + evaluations**, sessions revoked, critical
  audit. Courses/library remain accessible. Restricted login succeeds for
  learning and raises an admin alert.
- **Moderation queue**: reported forum posts, chat messages, question posts and
  stickers → staff approve/remove/warn/ban, all audited. Dictionary manager,
  restriction list/lift, banned-login alert panel. Responsibility disclaimer on
  forum and chat pages.
- **Migration/seed**: `database/migrations/003_communication.sql` +
  `tools/migrate_wave3.py` (idempotent, schema-drift guard). `seed_wave3()` seeds
  dictionary once, backfills division channels/memberships, and adds a demo forum
  thread. Existing databases are not relying on `create_all` alone.

## 2. Evidence (actual output)

```
check_i18n / check_served_secrets / check_fonts / check_enum_values /
check_sql_injection / check_schema_columns .... all PASS (46 tables, 336 columns)
migrate_wave3.py .............................. PASS (47 live tables incl. backup_records)

verify_wave0.py  == RESULT: 43/43 checks passed ==
verify_wave1.py  == RESULT: 32/32 checks passed ==
verify_wave2.py  == RESULT: 35/35 checks passed ==
verify_wave3.py  == RESULT: 98/98 checks passed ==
browser_smoke.py == BROWSER SMOKE: 34/34 passed ==
verify.sh        → VERIFY: ALL PASSED
```

Selected Wave-3 assertions (from `verify_wave3.py`):
```
[PASS] anonymous forum/chat APIs rejected (401)
[PASS] nested reply / unread count / GET does not mark read / explicit read clears unread
[PASS] locked thread rejects student reply / course thread ACLs
[PASS] question discussion requires submitted attempt / exam reference deep link
[PASS] cursor polling returns only newer messages / read state clears unread
[PASS] outsider cannot read or send to private channel
[PASS] block stops sender and recipient / unblock restores messaging
[PASS] clean text preserves casing
[PASS] division channel auto-membered / other division denied
[PASS] member downloads private image / outsider denied / private gateway headers
[PASS] disguised image rejected / upload quota enforced
[PASS] video range request supported (206) / document forced attachment download
[PASS] pending sticker hidden from others / student cannot approve / approved sticker sendable
[PASS] one submission counts one warning / profanity masked before storage
[PASS] third strike bans chat/evaluations / ban revokes existing sessions
[PASS] restricted user can still log in for courses / course access preserved
[PASS] evaluations blocked / forum blocked / admin alerted on restricted login
[PASS] owner lifts restriction / disabled dictionary word no longer filtered
[PASS] moderation queue snapshot / staff removes reported content / manual warning linked to report
```

Browser (from `browser_smoke.py`): forum index → create thread → reply → report
dialog; division chat channel → send message; owner moderation queue →
approve/dismiss → dictionary manager. **Zero console errors / zero failed
requests.** Screenshots: `docs/screenshots/23-forum.png`, `24-thread.png`,
`25-chat.png`, `26-moderation.png`.

## 3. Build size (cumulative, Wave 0 + 1 + 2 + 3)

| Metric | Count |
|---|---|
| Python files (app/) | 47 |
| Python LOC (app/) | 6,214 |
| Templates | 29 |
| JS files (static/js) | 18 |
| Arabic strings (`lang/ar.py`) | 754 |
| API endpoints | 122 |
| App DB tables / columns | 46 / 336 |
| Light themes | 3 |

## 4. Security/UX notes

- Light-only themes, measured logo palette, RTL Cairo, no inline styles, no
  emojis in product copy; all user-visible strings via `t()`.
- Scoped bans do **not** set `User.status=banned`; full-site bans still do.
- Private files are never static assets; downloads recheck parent ACLs.
- `TT.esc()` now escapes quotes for safe attribute interpolation.
- `[hidden]` is enforced globally so hidden panels cannot leak through flex/grid.
- Dev runtime can be rebuilt with `tools/setup_dev.sh` (venv + pgserver +
  Chromium from npm). The raw `*.e2b.app` preview URL remains token-gated; use
  the Arena Live Preview.

## 5. Known gaps (honest)

- Chat uses 5-second cursor polling, not WebSockets/push (per host constraint).
- Sticker approval is manual; no automated image-safety model yet.
- Profanity dictionary is a starter list, editable by staff; not exhaustive.
- Notifications, live streaming, paid settlement, admin builders/reports/cron,
  Gemini RAG/calendar are still Waves 4–6.
- `/admin/users` and `/admin/settings` remain placeholders until Wave 4.

## 6. Next

Wave 4: full admin/settings tree, builders (custom fields/dashboard/menu),
reports + exports, scheduled tasks/cron, and plugin/theme polish.
