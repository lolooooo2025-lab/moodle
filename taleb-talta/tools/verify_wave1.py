"""Wave-1 end-to-end verification (courses / lessons / library) against the real
PostgreSQL + live server. Run: python tools/verify_wave1.py
"""
from __future__ import annotations
import os, sys, random, pathlib
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

UA = {"User-Agent": "tt-verify-wave1/1.0"}

def main():
    print("== Taleb Talta Wave-1 verification ==")
    owner = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    r = owner.post("/api/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD}).json()
    check("owner login", r["success"], r["message"])
    OH = {"X-Sesskey": r["data"]["sesskey"]}

    # fresh student in division 1
    stu = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    phone = rand_phone()
    r = stu.post("/api/auth/register", json={"phone": phone, "password": STUDENT_PASSWORD,
                 "name": "طالب ويف", "guardian_phone": rand_phone(), "division_id": 1,
                 "website": "", "elapsed_ms": 5000}).json()
    check("student register", r["success"])
    r = stu.post("/api/auth/login", json={"phone": phone, "password": STUDENT_PASSWORD}).json()
    SH = {"X-Sesskey": r["data"]["sesskey"]}

    # ---- categories + course creation (capability-gated) ----
    r = stu.post("/api/courses", json={"title": "اختراق"}, headers=SH)
    check("student cannot create course (403)", r.status_code == 403)
    cat = owner.post("/api/categories", json={"name": "مادة اختبار " + str(random.randint(1000, 9999))}, headers=OH).json()
    check("owner creates category", cat["success"], cat["message"])
    cat_id = cat["data"]["id"]
    course = owner.post("/api/courses", json={"title": "كورس اختبار", "summary": "وصف",
                        "category_id": cat_id, "division_id": 1, "visibility": "visible"}, headers=OH).json()
    check("owner creates course", course["success"], course["message"])
    cid = course["data"]["id"]

    # ---- sections / lessons / items ----
    sec = owner.post(f"/api/courses/{cid}/sections", json={"title": "وحدة 1"}, headers=OH).json()
    check("add section", sec["success"]); sid = sec["data"]["id"]
    les = owner.post(f"/api/sections/{sid}/lessons", json={"title": "درس 1"}, headers=OH).json()
    check("add lesson", les["success"]); lid = les["data"]["id"]
    it_txt = owner.post(f"/api/lessons/{lid}/items", data={"item_type": "text", "title": "محتوى",
                        "body": "شرح الدرس"}, headers=OH).json()
    check("add text item", it_txt["success"]); txt_id = it_txt["data"]["id"]
    it_q = owner.post(f"/api/lessons/{lid}/items", data={"item_type": "question", "title": "سؤال",
                      "body": "١+١؟", "options": "1\n2\n3", "correct_index": 1}, headers=OH).json()
    check("add question item", it_q["success"]); q_id = it_q["data"]["id"]

    # ---- access control: student not enrolled yet ----
    r = stu.get(f"/api/lessons/{lid}")
    check("lesson blocked before enrolment (403)", r.status_code == 403)
    r = stu.post(f"/api/courses/{cid}/enrol", json={}, headers=SH).json()
    check("student enrols (free, division match)", r["success"], r["message"])
    r = stu.get(f"/api/lessons/{lid}").json()
    check("lesson accessible after enrolment", r["success"])
    q = [i for i in r["data"]["items"] if i["item_type"] == "question"][0]
    check("correct answer NOT sent to browser", "correct_index" not in q and "correct" not in q)

    # ---- progress + server-side grading ----
    r = stu.post(f"/api/lesson_items/{txt_id}/complete", json={}, headers=SH).json()
    check("complete text item", r["success"], f"progress={r['data']['progress']}")
    r = stu.post(f"/api/lesson_items/{q_id}/check", json={"choice": 0}, headers=SH).json()
    check("wrong answer graded wrong", r["data"]["correct"] is False, r["message"])
    r = stu.post(f"/api/lesson_items/{q_id}/check", json={"choice": 1}, headers=SH).json()
    check("right answer graded right", r["data"]["correct"] is True, r["message"])
    r = stu.get(f"/api/lessons/{lid}").json()
    check("lesson progress reaches 100", r["data"]["progress"] == 100, f"{r['data']['progress']}%")

    # ---- division gating: a division-2 student cannot enrol ----
    stu2 = httpx.Client(base_url=BASE, headers=UA, timeout=20)
    p2 = rand_phone()
    stu2.post("/api/auth/register", json={"phone": p2, "password": STUDENT_PASSWORD,
              "name": "طالب شعبة تانية", "guardian_phone": rand_phone(), "division_id": 2,
              "website": "", "elapsed_ms": 5000})
    r = stu2.post("/api/auth/login", json={"phone": p2, "password": STUDENT_PASSWORD}).json()
    H2 = {"X-Sesskey": r["data"]["sesskey"]}
    r = stu2.post(f"/api/courses/{cid}/enrol", json={}, headers=H2).json()
    check("other-division student blocked from enrolment", not r["success"], r["message"])

    # ---- library workflow ----
    r = stu.post("/api/library/submit", data={"title": "ملزمة اختبار", "description": "وصف",
                 "category": "فيزياء"}, files={"upload": ("note.txt", b"study note content", "text/plain")},
                 headers=SH).json()
    check("student submits library item", r["success"], r["message"]); lib_id = r["data"]["id"]
    r = stu.get("/api/library/pending")
    check("student cannot view moderation queue (403)", r.status_code == 403)
    pend = owner.get("/api/library/pending").json()
    check("pending queue shows item", any(i["id"] == lib_id for i in pend["data"]))
    # not yet in shared library
    shared = stu.get("/api/library").json()
    check("pending item not public yet", not any(i["id"] == lib_id for i in shared["data"]))
    # reject requires reason
    r = owner.post(f"/api/library/{lib_id}/reject", json={"reason": ""}, headers=OH).json()
    check("reject without reason refused", not r["success"], r["message"])
    r = owner.post(f"/api/library/{lib_id}/approve", json={}, headers=OH).json()
    check("moderator approves", r["success"], r["message"])
    shared = stu.get("/api/library").json()
    check("approved item now public", any(i["id"] == lib_id for i in shared["data"]))
    # download
    r = stu.get(f"/api/library/{lib_id}/download")
    check("approved file downloads", r.status_code == 200 and r.content == b"study note content")
    # private space
    r = stu.post(f"/api/library/{lib_id}/save", json={}, headers=SH).json()
    check("save to private space", r["success"], r["message"])
    mine = stu.get("/api/library/mine").json()
    check("private space lists item", len(mine["data"]) == 1)
    priv_id = mine["data"][0]["private_id"]
    r = stu.get(f"/api/library/private/{priv_id}/download")
    check("private download works", r.status_code == 200)
    r = stu2.get(f"/api/library/private/{priv_id}/download")
    check("other student cannot download private copy (403)", r.status_code == 403)

    # ---- soft delete ----
    r = owner.post(f"/api/courses/{cid}/delete", json={}, headers=OH).json()
    check("soft delete course", r["success"], r["message"])
    clist = owner.get("/api/courses").json()
    check("deleted course hidden from list", not any(c["id"] == cid for c in clist["data"]))

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok]); sys.exit(1)
    print("ALL WAVE-1 CHECKS PASSED")

if __name__ == "__main__":
    main()
