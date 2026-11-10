# Wave 4 report — Administration, customization, plugins

Status: **implemented — it runs.** Verified against real PostgreSQL and headless
Chromium. `bash verify.sh` exits 0. Full gate output: `docs/wave4-verify.log`.

## 1. What was built (prompt §6, Wave 4)

- **Consistent staff area**: shared admin sub-navigation, role-aware dashboard
  tiles, and capability-gated pages for users/divisions, settings, security,
  reports, tasks, backups, plugins and audit. Wave-5 areas (purchases,
  broadcasts, campaigns, live) are **explicit placeholders**, not fake tools.
- **Site settings tree**: general/branding, registration + maintenance toggles,
  owner-only security policy (lockout, session idle/absolute, password length /
  history), typed validation, CSRF, audit. Maintenance blocks student API/web/
  login while staff keep working. Non-active accounts cannot log in.
- **Custom-field builder**: user/course fields (text/number/select/checkbox),
  machine-name validation, required/enabled/order, select options, private vs
  shared values, rendered on profile and course forms, usable as report filters.
- **Dashboard builder**: per-role default blocks + per-user preferences
  (order/visibility), duplicate-order rejection, digest block.
- **Theme designer**: brand-palette presets (primary/secondary/accent/radius/
  density), activation, per-role override, generated `/theme.css`, base light
  themes still selectable. No arbitrary colours outside the measured palette.
- **Menu builder**: admin-managed internal links with icon/role/order/enabled;
  rejects `javascript:` and external URLs; plugin-managed entries protected.
- **Reports + exports**: enrolments, activity, grades (best attempt), usage,
  audit. Date window ≤366 days, half-open UTC; owner/admin all, teacher own
  courses, student denied. CSV (UTF-8 BOM + formula-injection guard) and real
  XLSX (RTL, frozen header, autofilter, brand header). Exports rate-limited and
  audited. Result cap 10,000 rows with `truncated` flag.
- **Plugin manager**: lifecycle present → installed → enabled/disabled,
  upgrade detection, typed plugin settings dialog, uninstall keep/purge.
  Ships the `tool_backup` plugin end-to-end.
- **Scheduled tasks**: 5-field cron parser (DOM-or-DOW), DB locks + 10-minute
  lease, run history, manual run, token-protected `/api/cron/run`, and a real
  worker (`python -m app.cron`). Tasks: cleanup, forum digest, scheduled backup.
  Cleanup removes expired sessions/tokens/rate-limits/login-attempts and only
  **unreferenced** old attachments (checks both chat messages and stickers).
- **Backups**: owner-only real `pg_dump` artifacts (+ optional uploads tar.gz),
  SHA-256 + size, download/delete, retention from plugin settings, 2 GiB cap.
  Archives exclude previous backups. Verified with `pg_restore --list`.
- **Migration/seed**: `database/migrations/004_administration.sql` +
  `tools/migrate_wave4.py` (idempotent, schema-drift guard). On older DBs run
  **migrate_wave4 before migrate_wave3** (Wave 3 validates full current metadata).

## 2. Evidence (actual output)

```
check_i18n / check_served_secrets / check_fonts / check_enum_values /
check_sql_injection / check_schema_columns .... all PASS (55 tables, 400 columns)
migrate_wave4.py .............................. PASS (56 live tables)
migrate_wave3.py .............................. PASS (56 live tables)

verify_wave0.py  == RESULT: 43/43 checks passed ==
verify_wave1.py  == RESULT: 32/32 checks passed ==
verify_wave2.py  == RESULT: 35/35 checks passed ==
verify_wave3.py  == RESULT: 98/98 checks passed ==
verify_wave4.py  == RESULT: 128/128 checks passed ==
browser_smoke.py == BROWSER SMOKE: 54/54 passed ==
verify.sh        → VERIFY: ALL PASSED   (390 checks total)
```

Selected Wave-4 assertions (from `verify_wave4.py`):
```
[PASS] maintenance blocks student API/web/login, keeps staff working, lifts cleanly
[PASS] admin cannot read owner security policy / out-of-range value rejected
[PASS] changed idle timeout enforced server-side / suspended login rejected
[PASS] required custom field enforced / course number validation / cross-user values denied
[PASS] dashboard order persists / duplicate order rejected / role defaults save
[PASS] arbitrary theme color rejected / active preset cannot be deleted / role override visible
[PASS] javascript and external menu URLs rejected / role-targeted menu hidden from others
[PASS] grade report uses best attempt / teacher cannot report outside owned courses
[PASS] CSV BOM / Excel RTL workbook / formula injection neutralized / export audited
[PASS] failed task history survives rollback / failed task releases its lock
[PASS] cleanup removes only unreferenced old attachments / preserves message+sticker attachments
[PASS] token-protected cron executes due tasks / background worker executes due task
[PASS] scheduled backup creates real dump / checksum matches / pg_restore can list it
[PASS] upload archive contains dump+storage and excludes previous backups
[PASS] W5 admin areas are honest placeholders / student cannot open them
```

Browser (from `browser_smoke.py`): admin users → settings tree → custom-field
builder → dashboard builder reorder/save → theme preset activate/revert/delete →
menu builder → security page → report filters + CSV/XLSX downloads → manual cron
run + history → backup create/download/delete → typed plugin settings → student
dashboard personalization → profile custom value persistence. **Zero console
errors / zero failed requests.** Screenshots: `docs/screenshots/27-admin-users.png`
through `34-profile-custom-fields.png`.

## 3. Build size (cumulative, Wave 0 + 1 + 2 + 3 + 4)

| Metric | Count |
|---|---|
| Python files (app/) | 58 |
| Python LOC (app/) | 8,753 |
| Templates | 39 |
| JS files (static/js) | 28 |
| Arabic strings (`lang/ar.py`) | 1,000 |
| API paths / operations | 161 / 178 |
| App DB tables / columns | 55 / 400 (live 56 incl. plugin table) |
| Light base themes | 3 (+ brand presets) |

## 4. Security/UX notes

- Every admin write is capability-gated, CSRF-checked and audited; owner-only
  security/backup/plugin-purge surfaces are separated from admin.
- Light-only RTL Cairo UI; all copy via `t()`; no inline styles; service worker
  caches static assets only (cache bumped to v6) and never authenticated HTML/API.
- Personal theme cookie overrides the site default by design; the browser test
  clears it when proving site-wide preset activation.
- Reports never expose another teacher's courses; audit export requires
  `audit/view`. Spreadsheet cells starting with `= + - @` are neutralized.
- Cron claims are durable; handler failure rolls back work but preserves a
  `failed` run and releases the lock (regression-tested).

## 5. Known gaps (honest)

- **Not all 18 legacy admin pages are separate/complete**: W0–W4 areas are
  consistent; divisions live inside Users, lessons inside course management;
  purchases/broadcasts/campaigns/live are marked Wave-5 placeholders.
- **Plugin ZIP upload is deferred** (owner-only arbitrary-code risk). The engine
  installs vetted on-disk packages; only `tool_backup` ships today. The prompt's
  block/report/local example plugins are not yet shipped.
- **Backups have no restore path** yet (create/download/delete/retention only).
- Privacy/GDPR anonymise-delete tooling and a full competency/badge framework
  remain unbuilt (P2).
- Audit admin page shows the latest 50 rows; full filtered export is via Reports.
- Cron needs the separate worker process running (`python -m app.cron`); the
  token HTTP endpoint is provided for hosts without long-lived processes.

## 6. Next

Wave 5: paid courses/lessons with manual settlement + server-enforced
`PAID_CONTENT_LOCKED`, live streaming with owner-only publish key, targeted
notifications and the Friday campaign/archive.
