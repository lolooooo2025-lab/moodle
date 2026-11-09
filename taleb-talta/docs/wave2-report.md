# Wave 2 report — Exams & grading

Status: **merged — it runs.** Verified against the real PostgreSQL database and a
headless Chromium browser. `verify.sh` exits 0.

## 1. What was built (prompt §6, Wave 2)

- **Question bank — all 6 types**: MCQ single, MCQ multi, true/false, short answer,
  matching, numeric. Admin question editor with per-type fields (options, correct
  index/indices, numeric value + tolerance, matching pairs).
- **Exams**: per-course, time limit (minutes, 0 = untimed), attempt limit (1..N,
  0 = unlimited), visibility, optional shuffle.
- **Attempts**: start/resume, server-enforced expiry, one-or-N attempts. Objective
  types auto-graded on the server; short answer flagged for **manual grading**.
- **Correct answers never reach the browser before submission.** `answer_json` is
  stripped from every student-facing payload (exam detail + attempt). Verified.
- **Gradebook**: per-course best marks, totals, ranking, **CSV export** (UTF-8 BOM so
  Arabic opens correctly in Excel).
- **Result review**: per-question verdict, your answer, the correct answer, an
  explanation box, and a **discussion thread attached to each question** (the spec's
  "مناقشة توضيحية"). Posts are capability-gated and audited.

## 2. Evidence (actual output)

```
check_i18n / check_enum_values / check_schema_columns / check_sql_injection /
check_served_secrets / check_fonts ............ all PASS (31 tables, 232 columns)

verify_wave0.py  == RESULT: 43/43 checks passed ==
verify_wave1.py  == RESULT: 32/32 checks passed ==
verify_wave2.py  == RESULT: 35/35 checks passed ==
browser_smoke.py == BROWSER SMOKE: 24/24 passed ==
verify.sh        → VERIFY: ALL PASSED
```

Selected Wave-2 assertions (from `verify_wave2.py`):
```
[PASS] student cannot author questions (403)
[PASS] author mcq_single / truefalse / numeric / mcq_multi / match question
[PASS] question with <2 options rejected
[PASS] exam detail hides answers from student
[PASS] attempt questions hide answers
[PASS] submit graded full marks — score=10.0
[PASS] review reveals answers + explanation after submit
[PASS] resubmit rejected / no attempts left after limit
[PASS] short answer awaits manual grading
[PASS] student cannot grade (403) / manual grade awards points
[PASS] timed attempt has expiry / late submit rejected (time_up)
[PASS] student cannot view gradebook (403) / gradebook CSV export
[PASS] post to question discussion / discussion lists post
[PASS] other-division student blocked from exam (403)
```

Browser (from `browser_smoke.py`): exams list → exam runner (all 5 demo types + timer)
→ submit → result → review with explanations; admin exam manager; gradebook.
**Zero console errors / zero failed requests.**

Screenshots: `docs/screenshots/18-exams-list`, `19-exam-runner`, `20-exam-review`,
`21-admin-exams`, `22-gradebook`.

## 3. Build size (cumulative, Wave 0 + 1 + 2)

| Metric | Count |
|---|---|
| Python files (app/) | 42 |
| Python LOC (app/) | 4,394 |
| Templates | 24 |
| Page scripts (JS) | 13 |
| Arabic strings (`lang/ar.py`) | 588 |
| API endpoints | 58 |
| DB tables | 31 |
| Light themes | 3 |

## 4. Known gaps (honest)
- Matching/numeric are auto-graded; **short answer is manual-only** (by design, per prompt).
- No exam-wide randomised question pool yet (shuffle reorders a fixed set).
- Gradebook export is CSV (Excel-compatible); native `.xlsx` is a later polish item.
- Forum/messages/chat, notifications, streaming, AI are **not built** (Waves 3–6).
- Preview access: the raw `*.e2b.app` URL is token-gated; use the Arena Live Preview.

## 5. Next
Wave 3: forum-style discussion, 1:1 messages, chat (1:1/group/division) with
attachments + stickers, profanity filter (mask + warn, 3rd → 30-day ban), moderation queue.
