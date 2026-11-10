# Wave 1 report — Courses, Lessons, Library + light-only redesign

Status: **merged — it runs.** Verified against the real PostgreSQL database and a
headless Chromium browser. `verify.sh` exits 0.

## 1. What changed this wave

### Redesign (user directive: no dark mode, use the PROMPT.md logo palette)
- Dark mode **removed**. `config.THEMES = ("light", "neutral", "sky")` — all three are
  light. Default is `light`. The old `navy` theme is gone and is no longer offered in
  the theme switcher (browser test asserts this).
- Colours come from `docs/logo-colors.json` (measured from the logo): blue `#0848A4`,
  cyan `#2FBCF9`, amber `#F8B43C`, neutrals `#EBEDF4 / #C5D0E3 / #9BA9B2`. Page
  background `#F7F8FB`, white cards, navy text. Semantic: success `#1E8E5A`,
  danger `#C0392B`, warning `#B9770E`.
- Rebuilt the design kit (`app.css`, 355 lines): cards, tiles with palette accent
  borders, chips/badges, progress bars, tabs, tables, forms. RTL + Cairo throughout.
- **CSP stays strict** (`style-src 'self'`, no `unsafe-inline`). All inline `style=""`
  attributes were removed and replaced with utility classes + CSSOM writes, so the
  browser runs with **zero console errors**.

### Wave 1 features (prompt §6.1–§6.11)
- **Courses**: categories, divisions, visibility, availability window, soft delete.
  Staff create/edit/delete; students browse + self-enrol (free, division-matched).
- **Lessons**: sections → lessons → items (text / file / link / question). Staff author
  via an in-player form; file uploads go through the secure file gateway.
- **Lesson player**: progress tracking, server-side MCQ grading. The correct answer is
  **never sent to the browser** (verified). Progress = completed items / total.
- **Library**: shared moderated library + private space. Submit → pending → approve /
  reject-with-reason. Download ACL + counters. Save-to-private + private download
  (owner-only). Offline save to IndexedDB.
- **Admin**: course/category management + library moderation queue.

## 2. Evidence (actual output)

```
check_i18n: PASS — no hard-coded Arabic outside lang/
check_enum_values: PASS — 8 enum fields, all literals valid
check_schema_columns: PASS — schema.sql in sync (25 tables, 179 columns)
check_served_secrets: PASS — 2 secrets checked, none served
check_fonts: PASS — 8 real font files (magic bytes verified)
check_sql_injection: PASS — no concatenated/f-string SQL in app/

verify_wave0.py  == RESULT: 43/43 checks passed ==
verify_wave1.py  == RESULT: 32/32 checks passed ==
browser_smoke.py == BROWSER SMOKE: 18/18 passed ==
verify.sh        → VERIFY: ALL PASSED
```

Selected Wave-1 assertions (from `verify_wave1.py`):
```
[PASS] student cannot create course (403)
[PASS] lesson blocked before enrolment (403)
[PASS] correct answer NOT sent to browser
[PASS] wrong answer graded wrong / right answer graded right
[PASS] other-division student blocked from enrolment
[PASS] pending item not public yet → approved item now public
[PASS] reject without reason refused
[PASS] other student cannot download private copy (403)
[PASS] soft delete course → hidden from list
```

Browser (from `browser_smoke.py`):
```
[PASS] default theme is light (no dark mode) — light
[PASS] no dark theme offered — ['light', 'neutral', 'sky']
[PASS] courses list / course detail / lesson player / library render
[PASS] zero console errors / zero failed requests
```

Screenshots: `docs/screenshots/01,03,11–17` (login, dashboard, courses list, course
detail, lesson player, library, private space, admin courses, admin library).

## 3. Build size (cumulative, Wave 0 + 1)

| Metric | Count |
|---|---|
| Python files (app/) | 41 |
| Python LOC (app/) | 3,635 |
| Templates | 19 |
| Page scripts (JS) | 8 |
| CSS lines | 355 |
| Arabic strings (`lang/ar.py`) | 512 |
| API endpoints | 43 |
| DB tables | 25 |
| Light themes | 3 |
| Example plugins | 1 (`tool_backup`) |

## 4. Known gaps (honest)
- **Paid enrolment** is locked (`price_cents > 0` → `err.paid_locked`); manual settlement
  is Wave 5.
- Admin course table shows raw category/division IDs (cosmetic; names resolve in the API).
- Library offline save stores to IndexedDB but has no offline browse/open UI yet (§6.11 partial).
- Exams, chat, notifications, streaming, AI are **not built** (Waves 2–3).
- Preview access: the raw `*.e2b.app` URL is token-gated; use the Arena Live Preview.

## 5. Next
Wave 2: MCQ exams + results, chat (sticker approval + profanity ban), targeted
notifications + Friday broadcast.
