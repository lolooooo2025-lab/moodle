"""Wave-2 end-to-end verification (exams & grading) against real PostgreSQL +
the live server. Run: python tools/verify_wave2.py
"""
from __future__ import annotations
import os, sys, random, pathlib, asyncio
import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
RESULTS = []

def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok

def rand_phone():
    return "011" + "".join(str(random.randint(0, 9)) for _ in range(8))

UA = {"User-Agent": "tt-verify-wave2/1.0"}

def register_student(division):
    c = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    phone = rand_phone()
    c.post("/api/auth/register", json={"phone": phone, "password": STUDENT_PASSWORD,
           "name": "طالب امتحان", "guardian_phone": rand_phone(), "division_id": division,
           "website": "", "elapsed_ms": 5000})
    r = c.post("/api/auth/login", json={"phone": phone, "password": STUDENT_PASSWORD}).json()
    return c, {"X-Sesskey": r["data"]["sesskey"]}

def main():
    print("== Taleb Talta Wave-2 verification ==")
    owner = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    r = owner.post("/api/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD}).json()
    check("owner login", r["success"]); OH = {"X-Sesskey": r["data"]["sesskey"]}
    # dedicated test course so the demo course stays pristine
    r = owner.post("/api/courses", json={"title": "كورس اختبار الامتحانات " + str(random.randint(1000, 9999)),
                   "division_id": 1, "visibility": "visible"}, headers=OH).json()
    check("create test course", r["success"]); cid = r["data"]["id"]

    stu, SH = register_student(1)
    r = stu.post(f"/api/courses/{cid}/enrol", json={}, headers=SH).json()
    check("student enrols in test course", r["success"])

    # ---- capability gate ----
    r = stu.post("/api/questions", json={"qtype": "mcq_single", "prompt": "x"}, headers=SH)
    check("student cannot author questions (403)", r.status_code == 403)

    # ---- author one question of each type ----
    defs = [
        {"qtype": "mcq_single", "prompt": "١+١؟", "options_json": ["1", "2", "3"], "answer_json": {"correct": 1}, "explanation": "اتنين"},
        {"qtype": "truefalse", "prompt": "السما زرقا؟", "answer_json": {"correct": True}},
        {"qtype": "numeric", "prompt": "١٠٠÷٥؟", "answer_json": {"value": 20, "tolerance": 0.1}},
        {"qtype": "mcq_multi", "prompt": "أنهي وحدات طاقة؟", "options_json": ["جول", "نيوتن", "سعر"], "answer_json": {"correct": [0, 2]}},
        {"qtype": "match", "prompt": "وصّل", "options_json": {"left": ["أ", "ب"], "right": ["١", ""]}, "answer_json": {"pairs": [[0, 1], [1, 0]]}},
    ]
    qids = {}
    for d in defs:
        d["course_id"] = cid
        r = owner.post("/api/questions", json=d, headers=OH).json()
        check(f"author {d['qtype']} question", r["success"], r["message"])
        qids[d["qtype"]] = r["data"]["id"]
    # invalid question rejected
    r = owner.post("/api/questions", json={"course_id": cid, "qtype": "mcq_single", "prompt": "x",
                   "options_json": ["only one"], "answer_json": {"correct": 0}}, headers=OH).json()
    check("question with <2 options rejected", not r["success"], r["message"])

    # ---- build an objective-only exam, 1 attempt ----
    r = owner.post("/api/exams", json={"course_id": cid, "title": "امتحان موضوعي",
                   "max_attempts": 1, "time_limit_minutes": 0}, headers=OH).json()
    check("create exam", r["success"]); eid = r["data"]["id"]
    for qt, qid in qids.items():
        r = owner.post(f"/api/exams/{eid}/questions", json={"question_id": qid, "points": 2}, headers=OH).json()
        check(f"add {qt} to exam", r["success"])
    # duplicate rejected
    r = owner.post(f"/api/exams/{eid}/questions", json={"question_id": qids['mcq_single']}, headers=OH).json()
    check("duplicate exam question rejected", not r["success"])

    # ---- answers never leak ----
    det = stu.get(f"/api/exams/{eid}").json()
    check("exam detail hides answers from student", all("answer" not in q for q in det["data"]["questions"]))
    r = stu.post(f"/api/exams/{eid}/start", json={}, headers=SH).json()
    check("start attempt", r["success"], r["message"]); att = r["data"]["attempt_id"]
    check("attempt questions hide answers", all("answer" not in q for q in r["data"]["questions"]))

    # ---- submit correct answers -> full marks, server graded ----
    answers = {
        str(qids["mcq_single"]): {"choice": 1},
        str(qids["truefalse"]): {"choice": True},
        str(qids["numeric"]): {"value": 20},
        str(qids["mcq_multi"]): {"choices": [0, 2]},
        str(qids["match"]): {"pairs": [[0, 1], [1, 0]]},
    }
    r = stu.post(f"/api/attempts/{att}/submit", json={"answers": answers}, headers=SH).json()
    check("submit graded full marks", r["success"] and r["data"]["score"] == 10 and r["data"]["status"] == "graded",
          f"score={r['data'].get('score')}")
    # wrong numeric on a fresh attempt is not possible (1 attempt) -> test review instead
    rev = stu.get(f"/api/attempts/{att}/review").json()
    check("review reveals answers + explanation after submit", rev["success"] and
          all("answer" in i for i in rev["data"]["items"]))
    # resubmit rejected
    r = stu.post(f"/api/attempts/{att}/submit", json={"answers": answers}, headers=SH).json()
    check("resubmit rejected", not r["success"], r["message"])
    # max attempts exhausted
    r = stu.post(f"/api/exams/{eid}/start", json={}, headers=SH).json()
    check("no attempts left after limit", not r["success"], r["message"])

    # ---- manual grading for short answer ----
    r = owner.post("/api/questions", json={"course_id": cid, "qtype": "short",
                   "prompt": "اشرح", "answer_json": {}}, headers=OH).json()
    short_q = r["data"]["id"]
    r = owner.post("/api/exams", json={"course_id": cid, "title": "امتحان مقالي", "max_attempts": 0}, headers=OH).json()
    eid2 = r["data"]["id"]
    owner.post(f"/api/exams/{eid2}/questions", json={"question_id": short_q, "points": 5}, headers=OH)
    r = stu.post(f"/api/exams/{eid2}/start", json={}, headers=SH).json(); att2 = r["data"]["attempt_id"]
    r = stu.post(f"/api/attempts/{att2}/submit", json={"answers": {str(short_q): {"text": "شرح طويل"}}}, headers=SH).json()
    check("short answer awaits manual grading", r["data"]["status"] == "submitted" and r["data"]["needs_manual"])
    r = stu.post(f"/api/attempts/{att2}/grade", json={"grades": {str(short_q): 4}}, headers=SH)
    check("student cannot grade (403)", r.status_code == 403)
    r = owner.post(f"/api/attempts/{att2}/grade", json={"grades": {str(short_q): 4}}, headers=OH).json()
    check("manual grade awards points", r["success"] and r["data"]["score"] == 4, f"score={r['data'].get('score')}")

    # ---- time limit enforced server-side ----
    r = owner.post("/api/exams", json={"course_id": cid, "title": "امتحان موقت",
                   "time_limit_minutes": 10, "max_attempts": 0}, headers=OH).json()
    eid3 = r["data"]["id"]
    owner.post(f"/api/exams/{eid3}/questions", json={"question_id": qids["truefalse"]}, headers=OH)
    r = stu.post(f"/api/exams/{eid3}/start", json={}, headers=SH).json()
    att3 = r["data"]["attempt_id"]
    check("timed attempt has expiry", r["data"]["expires_at"] is not None)
    # force expiry in the DB, then submit -> time_up
    async def expire():
        from app.core.db import get_sessionmaker
        from app.models import ExamAttempt, utcnow
        from sqlalchemy import select
        from datetime import timedelta
        async with get_sessionmaker()() as db:
            a = (await db.execute(select(ExamAttempt).where(ExamAttempt.id == att3))).scalar_one()
            a.expires_at = utcnow() - timedelta(minutes=1)
            await db.commit()
    asyncio.run(expire())
    r = stu.post(f"/api/attempts/{att3}/submit", json={"answers": {}}, headers=SH).json()
    check("late submit rejected (time_up)", not r["success"], r["message"])

    # ---- gradebook + export ----
    r = stu.get(f"/api/courses/{cid}/gradebook")
    check("student cannot view gradebook (403)", r.status_code == 403)
    gb = owner.get(f"/api/courses/{cid}/gradebook").json()
    check("gradebook has rows + ranking", gb["success"] and len(gb["data"]["rows"]) >= 1 and
          all("rank" in row for row in gb["data"]["rows"]))
    r = owner.get(f"/api/courses/{cid}/gradebook/export")
    check("gradebook CSV export", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""))

    # ---- per-question discussion ----
    r = stu.post(f"/api/questions/{qids['mcq_single']}/posts", json={"body": "ليه الإجابة اتنين؟"}, headers=SH).json()
    check("post to question discussion", r["success"], r["message"])
    posts = stu.get(f"/api/questions/{qids['mcq_single']}/posts").json()
    check("discussion lists post", posts["success"] and len(posts["data"]) >= 1)

    # ---- division gating ----
    stu2, H2 = register_student(2)
    r = stu2.post(f"/api/exams/{eid}/start", json={}, headers=H2)
    check("other-division student blocked from exam (403)", r.status_code == 403)

    # tidy up: soft-delete the dedicated test course
    owner.post(f"/api/courses/{cid}/delete", json={}, headers=OH)

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok]); sys.exit(1)
    print("ALL WAVE-2 CHECKS PASSED")

if __name__ == "__main__":
    main()
