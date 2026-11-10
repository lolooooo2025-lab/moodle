"""Wave-5 end-to-end verification: manual money, notifications, campaigns, live.

Live server + real PostgreSQL. Creates isolated fixtures and removes them.
External push delivery and external HLS encoding are NOT claimed here: push
fan-out logic is exercised with a local stub, and stream tests verify metadata,
ACLs, encrypted credentials, player payloads and live chat.
"""
from __future__ import annotations
import os, sys, random, pathlib, asyncio, base64, json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
RESULTS, PHONES = [], []
RUN = str(random.randint(100000, 999999))
MARK = "zzwave5-" + RUN
UA = {"User-Agent": "tt-verify-wave5/1.0"}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def phone():
    p = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    PHONES.append(p)
    return p


def client():
    return httpx.Client(base_url=BASE, headers=UA, timeout=60, follow_redirects=False)


def login(c, p, password=STUDENT_PASSWORD):
    r = c.post("/api/auth/login", json={"phone": p, "password": password}).json()
    if not r.get("success"):
        raise RuntimeError("login failed: " + str(r))
    return {"X-Sesskey": r["data"]["sesskey"]}, r["data"]["user_id"]


def register(name, division=1):
    c = client(); p = phone()
    r = c.post("/api/auth/register", json={"phone": p, "password": STUDENT_PASSWORD,
               "name": name, "guardian_phone": phone(), "division_id": division,
               "website": "", "elapsed_ms": 5000}).json()
    if not r.get("success"):
        raise RuntimeError("register failed: " + str(r))
    h, uid = login(c, p)
    return c, h, uid, p


def jpost(c, url, body, h):
    return c.post(url, json=body, headers=h).json()


def locked(r):
    if r.status_code != 403:
        return False
    try:
        return r.json().get("data", {}).get("code") == "PAID_CONTENT_LOCKED"
    except Exception:
        return False


async def db(fn):
    from app.core.db import get_sessionmaker, dispose_db
    try:
        async with get_sessionmaker()() as s:
            out = await fn(s)
            await s.commit()
            return out
    finally:
        await dispose_db()


async def set_role(p, role):
    from sqlalchemy import update
    from app.models import User
    async def fn(s):
        await s.execute(update(User).where(User.phone == p).values(role=role))
    await db(fn)


async def cleanup(user_ids, course_ids, campaign_ids, stream_ids):
    from sqlalchemy import text
    # Include any aborted earlier runs of this verifier (prefix is unique to it).
    async def fn(s):
        async def ids(sql):
            return [r[0] for r in (await s.execute(text(sql))).all()]
        users = await ids("SELECT id FROM users WHERE name LIKE 'zzwave5-%'")
        courses = await ids("SELECT id FROM courses WHERE title LIKE 'zzwave5-%'")
        campaigns = await ids("SELECT id FROM campaigns WHERE title LIKE 'zzwave5-%'")
        streams = await ids("SELECT id FROM live_streams WHERE title LIKE 'zzwave5-%'")
        def in_list(table, col, values):
            if values:
                return f"DELETE FROM {table} WHERE {col} IN ({','.join(str(int(v)) for v in values)})"
            return None
        async def run(*stmts):
            for stmt in stmts:
                if stmt:
                    await s.execute(text(stmt))
        channels = await ids(f"SELECT chat_channel_id FROM live_streams WHERE id IN ({','.join(map(str, streams))})") if streams else []
        channels = [c for c in channels if c]
        lessons = await ids(f"SELECT l.id FROM lessons l JOIN course_sections cs ON cs.id=l.section_id WHERE cs.course_id IN ({','.join(map(str, courses))})") if courses else []
        exams = await ids(f"SELECT id FROM exams WHERE course_id IN ({','.join(map(str, courses))})") if courses else []
        questions = await ids(f"SELECT id FROM questions WHERE course_id IN ({','.join(map(str, courses))})") if courses else []
        threads = await ids(f"SELECT id FROM discussion_threads WHERE course_id IN ({','.join(map(str, courses))})") if courses else []
        attempts = await ids(f"SELECT id FROM exam_attempts WHERE exam_id IN ({','.join(map(str, exams))})") if exams else []
        nids = set(await ids(f"SELECT notification_id FROM notification_recipients WHERE user_id IN ({','.join(map(str, users))})") if users else [])
        nids.update(await ids("SELECT id FROM notifications WHERE title LIKE 'zzwave5-%'"))
        if campaigns:
            nids.update(await ids(f"SELECT id FROM notifications WHERE campaign_id IN ({','.join(map(str, campaigns))})"))
        if users:
            nids.update(await ids(f"SELECT id FROM notifications WHERE created_by IN ({','.join(map(str, users))})"))
        await run(in_list("notification_recipients", "notification_id", list(nids)),
                  in_list("notification_recipients", "user_id", users), in_list("notifications", "id", list(nids)),
                  in_list("notifications", "campaign_id", campaigns),
                  "DELETE FROM notifications WHERE title LIKE 'zzwave5-%'",
                  in_list("push_subscriptions", "user_id", users), in_list("purchases", "user_id", users),
                  in_list("purchases", "course_id", courses),
                  in_list("attempt_answers", "attempt_id", attempts), in_list("exam_attempts", "exam_id", exams),
                  in_list("exam_attempts", "user_id", users), in_list("exam_questions", "exam_id", exams),
                  in_list("question_posts", "question_id", questions), in_list("attempt_answers", "question_id", questions),
                  in_list("discussion_posts", "thread_id", threads), in_list("forum_subscriptions", "thread_id", threads),
                  in_list("discussion_threads", "course_id", courses),
                  in_list("lesson_progress", "lesson_id", lessons), in_list("lesson_progress", "user_id", users),
                  in_list("lesson_items", "lesson_id", lessons), in_list("lessons", "id", lessons),
                  in_list("course_sections", "course_id", courses), in_list("course_students", "course_id", courses),
                  in_list("course_students", "user_id", users),
                  in_list("chat_messages", "channel_id", channels), in_list("chat_messages", "sender_id", users),
                  in_list("channel_members", "channel_id", channels), in_list("channel_members", "user_id", users),
                  in_list("direct_contacts", "channel_id", channels), in_list("direct_contacts", "user_id", users),
                  in_list("live_streams", "id", streams), in_list("channels", "id", channels),
                  in_list("attachments", "owner_id", users), in_list("user_library", "user_id", users),
                  in_list("digest_deliveries", "user_id", users), in_list("dashboard_preferences", "user_id", users),
                  in_list("sessions", "user_id", users), in_list("password_history", "user_id", users),
                  in_list("password_reset_tokens", "user_id", users), in_list("user_capability_overrides", "user_id", users),
                  in_list("moderation_strikes", "user_id", users), in_list("user_restrictions", "user_id", users),
                  in_list("exam_questions", "question_id", questions), in_list("question_posts", "user_id", users),
                  in_list("exams", "id", exams), in_list("questions", "id", questions),
                  in_list("courses", "id", courses), in_list("campaigns", "id", campaigns),
                  in_list("users", "id", users))
    await db(fn)


async def campaign_publish_due():
    from app.core import notifications
    async def fn(s):
        return await notifications.publish_due_campaigns(s)
    return await db(fn)


async def push_dispatch(stub, target=None):
    from app.core import notifications
    async def fn(s):
        with patch("pywebpush.webpush", stub):
            return await notifications.dispatch_push(s)
    totals = {"sent": 0, "failed": 0, "removed": 0, "skipped": 0, "recipients": 0}
    for _ in range(100):
        out = await db(fn)
        for key in totals:
            totals[key] += out.get(key, 0)
        if target is None:
            return totals
        st = await recipient_status(*target)
        if st and st[0] != "pending":
            return totals
    return totals


async def stream_row(sid):
    from sqlalchemy import select
    from app.models import LiveStream
    async def fn(s):
        r = (await s.execute(select(LiveStream).where(LiveStream.id == sid))).scalar_one()
        return {"key": r.publish_key_encrypted, "ingest": r.ingest_url_encrypted, "status": r.status}
    return await db(fn)


async def make_campaign_due(cid):
    from sqlalchemy import update
    from app.models import Campaign, utcnow
    async def fn(s):
        await s.execute(update(Campaign).where(Campaign.id == cid).values(publish_at=utcnow() - timedelta(minutes=1)))
    await db(fn)


async def recipient_status(nid, uid):
    from sqlalchemy import select
    from app.models import NotificationRecipient
    async def fn(s):
        r = (await s.execute(select(NotificationRecipient).where(NotificationRecipient.notification_id == nid,
            NotificationRecipient.user_id == uid))).scalar_one_or_none()
        return (r.push_status, r.read_at is not None) if r else None
    return await db(fn)


def main():
    user_ids, course_ids, campaign_ids, stream_ids = [], [], [], []
    asyncio.run(cleanup([], [], [], []))
    owner = client(); OH, OID = login(owner, OWNER_PHONE, OWNER_PASSWORD)
    stuA, HA, AID, PA = register(MARK + "-studentA", 1)
    stuB, HB, BID, PB = register(MARK + "-studentB", 2)
    admin, HA2, A2ID, PA2 = register(MARK + "-admin", 1)
    teacher, HT, TID, PT = register(MARK + "-teacher", 1)
    user_ids = [AID, BID, A2ID, TID]
    asyncio.run(set_role(PA2, "admin")); asyncio.run(set_role(PT, "teacher"))
    # re-login so session fingerprints/role changes are picked up cleanly
    HA2, _ = login(admin, PA2); HT, _ = login(teacher, PT)
    try:
        # ---------- pages and capability gates ----------
        for path in ("/admin/purchases", "/admin/broadcasts", "/admin/campaigns", "/admin/live"):
            check("owner page " + path, owner.get(path, headers=OH).status_code == 200)
        for path in ("/notifications", "/purchases", "/campaigns", "/live"):
            check("student page " + path, stuA.get(path, headers=HA).status_code == 200)
        check("student cannot review purchases", stuA.get("/api/admin/purchases", headers=HA).status_code == 403)
        check("student cannot compose broadcasts", stuA.post("/api/admin/notifications", json={"title": "x", "body": "y"}, headers=HA).status_code == 403)
        check("teacher cannot manage streams", teacher.get("/api/admin/streams", headers=HT).status_code == 403)
        check("admin cannot reveal publish key", admin.get("/api/admin/streams/1/credentials", headers=HA2).status_code in (403, 404))
        check("CSRF required for purchase request", stuA.post("/api/purchases", json={"course_id": 1, "reference": "abc"}).status_code == 403)

        # ---------- paid course fixtures ----------
        r = jpost(owner, "/api/courses", {"title": MARK + "-paid", "summary": "paid course", "division_id": 1}, OH)
        check("create paid-course fixture", r["success"]); cid = r["data"]["id"]; course_ids.append(cid)
        r = jpost(owner, f"/api/courses/{cid}/pricing", {"price_cents": 15000}, OH)
        check("owner sets course price", r["success"] and r["data"]["price_cents"] == 15000)
        check("teacher cannot price course", stuA.post(f"/api/courses/{cid}/pricing", json={"price_cents": 1}, headers=HT).status_code == 403)
        check("negative price rejected", owner.post(f"/api/courses/{cid}/pricing", json={"price_cents": -1}, headers=OH).status_code == 422)
        check("float price rejected", owner.post(f"/api/courses/{cid}/pricing", json={"price_cents": 1.5}, headers=OH).status_code == 422)
        sid = jpost(owner, f"/api/courses/{cid}/sections", {"title": MARK + "-sec"}, OH)["data"]["id"]
        lid = jpost(owner, f"/api/sections/{sid}/lessons", {"title": MARK + "-lesson"}, OH)["data"]["id"]
        lid2 = jpost(owner, f"/api/sections/{sid}/lessons", {"title": MARK + "-lesson2"}, OH)["data"]["id"]
        item = owner.post(f"/api/lessons/{lid}/items", data={"item_type": "text", "title": "secret", "body": MARK + "-content"}, headers=OH).json()["data"]["id"]
        qitem = owner.post(f"/api/lessons/{lid}/items", data={"item_type": "question", "title": "q", "body": "1+1?", "options": "1\n2", "correct_index": "1"}, headers=OH).json()["data"]["id"]
        fitem = owner.post(f"/api/lessons/{lid}/items", data={"item_type": "file", "title": "file"}, files={"upload": ("note.txt", b"paid file", "text/plain")}, headers=OH).json()["data"]["id"]
        qid = jpost(owner, "/api/questions", {"course_id": cid, "qtype": "mcq_single", "prompt": "1+1?", "options_json": ["1", "2"], "answer_json": {"correct": 1}}, OH)["data"]["id"]
        eid = jpost(owner, "/api/exams", {"course_id": cid, "title": MARK + "-exam"}, OH)["data"]["id"]
        jpost(owner, f"/api/exams/{eid}/questions", {"question_id": qid, "points": 1}, OH)

        r = stuA.post(f"/api/courses/{cid}/enrol", json={}, headers=HA)
        check("self-enrol into paid course locked", locked(r), str(r.status_code))
        for name, resp in (
            ("lesson", stuA.get(f"/api/lessons/{lid}", headers=HA)),
            ("item file", stuA.get(f"/api/lesson_items/{fitem}/file", headers=HA)),
            ("item complete", stuA.post(f"/api/lesson_items/{item}/complete", json={}, headers=HA)),
            ("item check", stuA.post(f"/api/lesson_items/{qitem}/check", json={"choice": 1}, headers=HA)),
            ("lesson complete", stuA.post(f"/api/lessons/{lid}/complete", json={}, headers=HA)),
            ("exam detail", stuA.get(f"/api/exams/{eid}", headers=HA)),
            ("exam start", stuA.post(f"/api/exams/{eid}/start", json={}, headers=HA)),
            ("exam list", stuA.get(f"/api/exams?course_id={cid}", headers=HA)),
            ("question discussion", stuA.get(f"/api/questions/{qid}/posts", headers=HA)),
            ("question post", stuA.post(f"/api/questions/{qid}/posts", json={"body": "why?"}, headers=HA)),
        ):
            check("paid lock on " + name, locked(resp), str(resp.status_code))
        detail = stuA.get(f"/api/courses/{cid}/detail", headers=HA).json()["data"]
        check("course header visible but locked", detail["price_cents"] == 15000 and not detail["can_learn"])
        check("locked lesson serialised as locked", all(l["locked"] for s in detail["sections"] for l in s["lessons"]))

        # request does not unlock; confirmation does
        check("whitespace reference rejected", stuA.post("/api/purchases", json={"course_id": cid, "reference": "   "}, headers=HA).status_code == 422)
        r = jpost(stuA, "/api/purchases", {"course_id": cid, "reference": "TX-" + RUN, "note": "manual transfer"}, HA)
        check("purchase request created", r["success"] and r["data"]["status"] == "pending"); pid = r["data"]["id"]
        check("pending request still locks lesson", locked(stuA.get(f"/api/lessons/{lid}", headers=HA)))
        r = jpost(stuA, "/api/purchases", {"course_id": cid, "reference": "TX-dup"}, HA)
        check("duplicate pending request rejected", not r["success"])
        check("student cannot confirm own purchase", stuA.post(f"/api/admin/purchases/{pid}/confirm", json={}, headers=HA).status_code == 403)
        queue = admin.get("/api/admin/purchases?status=pending", headers=HA2).json()["data"]
        check("admin queue shows request", any(p["id"] == pid for p in queue["rows"]))
        r = jpost(admin, f"/api/admin/purchases/{pid}/confirm", {"note": "verified"}, HA2)
        check("admin confirms purchase", r["success"] and r["data"]["status"] == "confirmed")
        check("confirmed purchase unlocks lesson", stuA.get(f"/api/lessons/{lid}", headers=HA).status_code == 200)
        check("confirmed purchase unlocks file", stuA.get(f"/api/lesson_items/{fitem}/file", headers=HA).status_code == 200)
        check("confirmed purchase unlocks exam", stuA.get(f"/api/exams/{eid}", headers=HA).status_code == 200)
        check("confirmed purchase unlocks exam list", stuA.get(f"/api/exams?course_id={cid}", headers=HA).status_code == 200)
        check("confirmed purchase unlocks question discussion", stuA.get(f"/api/questions/{qid}/posts", headers=HA).status_code == 200)
        check("confirmed purchase unlocks sibling lesson", stuA.get(f"/api/lessons/{lid2}", headers=HA).status_code == 200)
        check("other student still locked", locked(stuB.get(f"/api/lessons/{lid}", headers=HB)))
        check("double confirm rejected", not jpost(admin, f"/api/admin/purchases/{pid}/confirm", {}, HA2)["success"])
        inbox = stuA.get("/api/notifications", headers=HA).json()["data"]
        check("purchase confirmation notification", any(n["kind"] == "purchase" for n in inbox["rows"]))
        check("owner bypasses paid lock", owner.get(f"/api/lessons/{lid}", headers=OH).status_code == 200)

        # reject + cancel flows
        r = jpost(teacher, "/api/purchases", {"course_id": cid, "reference": "TX-B-" + RUN}, HT)
        pidB = r["data"]["id"]
        check("reject requires reason", admin.post(f"/api/admin/purchases/{pidB}/reject", json={"note": ""}, headers=HA2).status_code == 422)
        r = jpost(admin, f"/api/admin/purchases/{pidB}/reject", {"note": "reference not found"}, HA2)
        check("admin rejects purchase", r["success"] and r["data"]["status"] == "rejected")
        check("rejected purchase stays locked", locked(teacher.get(f"/api/lessons/{lid}", headers=HT)))
        r = jpost(teacher, "/api/purchases", {"course_id": cid, "reference": "TX-B2-" + RUN}, HT)
        pidB2 = r["data"]["id"]
        check("student cancels pending request", jpost(teacher, f"/api/purchases/{pidB2}/cancel", {}, HT)["success"])
        check("other student cannot cancel request", stuA.post(f"/api/purchases/{pidB2}/cancel", json={}, headers=HA).status_code == 404)

        # ---------- per-lesson pricing ----------
        r = jpost(owner, "/api/courses", {"title": MARK + "-perlesson", "division_id": 1}, OH)
        cid2 = r["data"]["id"]; course_ids.append(cid2)
        sid2 = jpost(owner, f"/api/courses/{cid2}/sections", {"title": "sec"}, OH)["data"]["id"]
        pl1 = jpost(owner, f"/api/sections/{sid2}/lessons", {"title": MARK + "-pl1"}, OH)["data"]["id"]
        pl2 = jpost(owner, f"/api/sections/{sid2}/lessons", {"title": MARK + "-pl2"}, OH)["data"]["id"]
        check("set lesson price", jpost(owner, f"/api/lessons/{pl1}/pricing", {"price_cents": 5000}, OH)["success"])
        check("set second lesson price", jpost(owner, f"/api/lessons/{pl2}/pricing", {"price_cents": 7000}, OH)["success"])
        check("mixed course+lesson pricing rejected", owner.post(f"/api/courses/{cid2}/pricing", json={"price_cents": 100}, headers=OH).status_code == 422)
        check("free course enrolment", jpost(stuA, f"/api/courses/{cid2}/enrol", {}, HA)["success"])
        check("paid lesson locked in free course", locked(stuA.get(f"/api/lessons/{pl1}", headers=HA)))
        r = jpost(stuA, "/api/purchases", {"course_id": cid2, "lesson_id": pl1, "reference": "LTX-" + RUN}, HA)
        check("per-lesson request created", r["success"] and r["data"]["amount_cents"] == 5000); plpid = r["data"]["id"]
        check("admin confirms per-lesson purchase", jpost(admin, f"/api/admin/purchases/{plpid}/confirm", {}, HA2)["success"])
        check("purchased lesson unlocks", stuA.get(f"/api/lessons/{pl1}", headers=HA).status_code == 200)
        check("sibling lesson remains locked", locked(stuA.get(f"/api/lessons/{pl2}", headers=HA)))
        check("lesson purchase cannot target paid course", not jpost(stuB, "/api/purchases", {"course_id": cid, "lesson_id": lid, "reference": "bad"}, HB)["success"])

        # ---------- targeted notifications ----------
        meta = owner.get("/api/admin/notifications/meta", headers=OH).json()["data"]
        check("notification meta has audiences", set(meta["audiences"]) == {"all", "role", "division", "course", "user"})
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-user", "body": "hello A", "audience": "user", "user_id": AID}, OH)
        check("send individual notification", r["success"] and r["data"]["recipients"] == 1); nid_user = r["data"]["id"]
        check("target user receives", any(n["id"] == nid_user for n in stuA.get("/api/notifications", headers=HA).json()["data"]["rows"]))
        check("non-target does not receive", not any(n["id"] == nid_user for n in stuB.get("/api/notifications", headers=HB).json()["data"]["rows"]))
        check("non-target cannot mark read", stuB.post(f"/api/notifications/{nid_user}/read", json={}, headers=HB).status_code == 403)
        check("mark read", jpost(stuA, f"/api/notifications/{nid_user}/read", {}, HA)["success"])
        st = asyncio.run(recipient_status(nid_user, AID))
        check("per-user read state persisted", st and st[1])
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-div", "body": "division one", "audience": "division", "division_id": 1}, OH)
        check("division notification sent", r["success"] and r["data"]["recipients"] >= 1)
        check("division target excludes other division", not any(n["title"] == MARK + "-div" for n in stuB.get("/api/notifications", headers=HB).json()["data"]["rows"]))
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-course", "body": "course members", "audience": "course", "course_id": cid}, OH)
        check("course notification sent", r["success"] and r["data"]["recipients"] >= 1)
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-role", "body": "students", "audience": "role", "role": "student"}, OH)
        check("role notification sent", r["success"] and r["data"]["recipients"] >= 2)
        check("invalid audience rejected", owner.post("/api/admin/notifications", json={"title": "x", "body": "y", "audience": "bogus"}, headers=OH).status_code == 422)
        check("mark all read", jpost(stuA, "/api/notifications/read-all", {}, HA)["success"])
        check("unread count drops", stuA.get("/api/notifications/unread", headers=HA).json()["data"]["unread"] == 0)

        # ---------- Friday campaign ----------
        today = datetime.now(timezone.utc).date()
        friday = today + timedelta(days=(4 - today.weekday()) % 7)
        if friday < today:
            friday += timedelta(days=7)
        r = jpost(owner, "/api/admin/campaigns", {"week_date": friday.isoformat(), "title": MARK + "-friday", "body": "same body for everyone"}, OH)
        check("schedule Friday campaign", r["success"]); camp = r["data"]["id"]; campaign_ids.append(camp)
        check("non-Friday rejected", owner.post("/api/admin/campaigns", json={"week_date": (friday + timedelta(days=1)).isoformat(), "title": "x", "body": "y"}, headers=OH).status_code == 422)
        check("duplicate week rejected", owner.post("/api/admin/campaigns", json={"week_date": friday.isoformat(), "title": "x", "body": "y"}, headers=OH).status_code == 409)
        check("early manual publish rejected", owner.post(f"/api/admin/campaigns/{camp}/publish", json={}, headers=OH).status_code == 409)
        check("campaign not in archive before publish", not any(c["id"] == camp for c in stuA.get("/api/campaigns", headers=HA).json()["data"]))
        asyncio.run(make_campaign_due(camp))
        out = asyncio.run(campaign_publish_due())
        check("cron publishes due campaign", out["campaigns"] >= 1)
        archA = stuA.get("/api/campaigns", headers=HA).json()["data"]
        archB = stuB.get("/api/campaigns", headers=HB).json()["data"]
        ca = next(c for c in archA if c["id"] == camp); cb = next(c for c in archB if c["id"] == camp)
        check("campaign identical for all users", ca["title"] == cb["title"] and ca["body"] == cb["body"])
        check("campaign unread for both", not ca["read"] and not cb["read"])
        check("campaign counted once in unread total", stuA.get("/api/notifications/unread", headers=HA).json()["data"]["unread"] == 1)
        check("campaign detail page", stuA.get(f"/campaigns/{camp}", headers=HA).status_code == 200)
        check("campaign read is per-user", jpost(stuA, f"/api/notifications/{ca['notification_id']}/read", {}, HA)["success"])
        ca2 = next(c for c in stuA.get("/api/campaigns", headers=HA).json()["data"] if c["id"] == camp)
        cb2 = next(c for c in stuB.get("/api/campaigns", headers=HB).json()["data"] if c["id"] == camp)
        check("campaign read state isolated", ca2["read"] and not cb2["read"])
        out2 = asyncio.run(campaign_publish_due())
        check("campaign publish idempotent", out2["campaigns"] == 0)
        check("published campaign not editable", owner.post(f"/api/admin/campaigns/{camp}", json={"week_date": friday.isoformat(), "title": "x", "body": "y"}, headers=OH).status_code == 409)

        # ---------- live streams ----------
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        secret_key = "publish-" + RUN + "-secret"
        r = jpost(owner, "/api/admin/streams", {"title": MARK + "-all", "description": "desc", "audience": "all",
                  "scheduled_at": future, "playback_url": "https://cdn.example.com/live/master.m3u8",
                  "ingest_url": "rtmps://ingest.example.com/live", "publish_key": secret_key}, OH)
        check("create scheduled stream", r["success"]); stream = r["data"]["id"]; stream_ids.append(stream)
        row = asyncio.run(stream_row(stream))
        check("publish key encrypted at rest", secret_key not in row["key"] and row["key"].startswith("fernet-v1:"))
        check("ingest URL encrypted at rest", "rtmps://ingest" not in row["ingest"] and row["ingest"].startswith("fernet-v1:"))
        pub = stuA.get(f"/api/streams/{stream}", headers=HA).json()["data"]
        check("scheduled stream hides playback URL", pub["status"] == "scheduled" and pub["playback_url"] == "")
        check("public payload has no credentials", "publish_key" not in pub and "publish_key_encrypted" not in pub and secret_key not in json.dumps(pub))
        check("admin list hides credentials", secret_key not in admin.get("/api/admin/streams", headers=HA2).text)
        managed = next(s for s in admin.get("/api/admin/streams", headers=HA2).json()["data"] if s["id"] == stream)
        check("manager can edit scheduled playback URL", managed["playback_url"] == "https://cdn.example.com/live/master.m3u8")
        edit = {"title": MARK + "-all", "description": "desc", "audience": "all", "scheduled_at": future,
                "playback_url": managed["playback_url"]}
        check("scheduled stream edit succeeds", jpost(owner, f"/api/admin/streams/{stream}", edit, OH)["success"])
        check("stream edit preserves playback URL", next(s for s in owner.get("/api/admin/streams", headers=OH).json()["data"] if s["id"] == stream)["playback_url"] == edit["playback_url"])
        check("whitespace stream title rejected", owner.post("/api/admin/streams", json={"title": "   ", "scheduled_at": future}, headers=OH).status_code == 422)
        check("playback URL non-443 port rejected", owner.post("/api/admin/streams", json={"title": "x", "scheduled_at": future, "playback_url": "https://cdn.example.com:8443/a.m3u8"}, headers=OH).status_code == 422)
        check("admin cannot reveal key", admin.get(f"/api/admin/streams/{stream}/credentials", headers=HA2).status_code == 403)
        check("student cannot reveal key", stuA.get(f"/api/admin/streams/{stream}/credentials", headers=HA).status_code == 403)
        creds = owner.get(f"/api/admin/streams/{stream}/credentials", headers=OH).json()["data"]
        check("owner reveals exact key", creds["publish_key"] == secret_key and creds["ingest_url"] == "rtmps://ingest.example.com/live")
        r = jpost(owner, "/api/admin/streams", {"title": MARK + "-nopb", "audience": "all", "scheduled_at": future}, OH)
        snopb = r["data"]["id"]; stream_ids.append(snopb)
        check("start requires playback URL", owner.post(f"/api/admin/streams/{snopb}/status", json={"action": "start"}, headers=OH).status_code == 422)
        r = jpost(owner, f"/api/admin/streams/{stream}/status", {"action": "start"}, OH)
        check("owner starts stream", r["success"] and r["data"]["status"] == "live")
        pub = stuA.get(f"/api/streams/{stream}", headers=HA).json()["data"]
        check("live audience gets playback URL", pub["playback_url"] == "https://cdn.example.com/live/master.m3u8" and pub["can_watch"])
        check("live chat enabled", pub["can_chat"])
        ch = pub["chat_channel_id"]
        check("live chat send", jpost(stuA, f"/api/chat/channels/{ch}/messages", {"body": MARK + "-chat"}, HA)["success"])
        msgs = stuB.get(f"/api/chat/channels/{ch}/messages", headers=HB).json()["data"]
        check("live chat shared with audience", any(m["body"] == MARK + "-chat" for m in msgs["messages"]))
        check("player page serves hls.js", "hls.min.js" in stuA.get(f"/live/{stream}", headers=HA).text)
        rot = jpost(owner, f"/api/admin/streams/{stream}/rotate-key", {}, OH)
        check("owner rotates key", rot["success"] and rot["data"]["publish_key"] != secret_key)
        check("rotated key not in public payload", rot["data"]["publish_key"] not in stuA.get(f"/api/streams/{stream}", headers=HA).text)
        check("admin cannot rotate key", admin.post(f"/api/admin/streams/{stream}/rotate-key", json={}, headers=HA2).status_code == 403)

        r = jpost(owner, "/api/admin/streams", {"title": MARK + "-div", "audience": "division", "division_id": 1,
                  "scheduled_at": future, "playback_url": "https://cdn.example.com/div.m3u8"}, OH)
        sdiv = r["data"]["id"]; stream_ids.append(sdiv)
        jpost(owner, f"/api/admin/streams/{sdiv}/status", {"action": "start"}, OH)
        check("division stream visible to matching division", stuA.get(f"/api/streams/{sdiv}", headers=HA).status_code == 200)
        check("division stream hidden from other division", stuB.get(f"/api/streams/{sdiv}", headers=HB).status_code == 403)
        dch = stuA.get(f"/api/streams/{sdiv}", headers=HA).json()["data"]["chat_channel_id"]
        check("division live chat ACL", stuB.get(f"/api/chat/channels/{dch}/messages", headers=HB).status_code == 403)
        check("division stream absent from other list", not any(s["id"] == sdiv for s in stuB.get("/api/streams", headers=HB).json()["data"]))

        r = jpost(owner, "/api/admin/streams", {"title": MARK + "-course", "audience": "course", "course_id": cid,
                  "scheduled_at": future, "playback_url": "https://cdn.example.com/course.m3u8"}, OH)
        scourse = r["data"]["id"]; stream_ids.append(scourse)
        jpost(owner, f"/api/admin/streams/{scourse}/status", {"action": "start"}, OH)
        check("paid-course stream unlocks for confirmed buyer", stuA.get(f"/api/streams/{scourse}", headers=HA).status_code == 200)
        check("paid-course stream locked for non-buyer", stuB.get(f"/api/streams/{scourse}", headers=HB).status_code == 403)
        check("invalid playback URL rejected", owner.post("/api/admin/streams", json={"title": "x", "scheduled_at": future, "playback_url": "http://x/a.m3u8"}, headers=OH).status_code == 422)
        check("end stream", jpost(owner, f"/api/admin/streams/{stream}/status", {"action": "end"}, OH)["success"])
        check("ended stream chat closed", stuA.post(f"/api/chat/channels/{ch}/messages", json={"body": "late"}, headers=HA).status_code == 409)
        check("ended stream hides playback", stuA.get(f"/api/streams/{stream}", headers=HA).json()["data"]["playback_url"] == "")
        check("invalid transition rejected", owner.post(f"/api/admin/streams/{stream}/status", json={"action": "start"}, headers=OH).status_code == 409)
        r = jpost(owner, "/api/admin/streams", {"title": MARK + "-cancel", "audience": "all", "scheduled_at": future}, OH)
        scancel = r["data"]["id"]; stream_ids.append(scancel)
        check("cancel scheduled stream", jpost(owner, f"/api/admin/streams/{scancel}/status", {"action": "cancel"}, OH)["success"])
        check("cancelled stream forbidden", stuA.get(f"/api/streams/{scancel}", headers=HA).status_code == 403)

        # ---------- Web Push local logic (no external delivery claim) ----------
        key = stuA.get("/api/notifications/push/key", headers=HA).json()["data"]["public_key"]
        pad = key + "=" * (-len(key) % 4)
        check("VAPID public key is P-256 point", len(base64.urlsafe_b64decode(pad)) == 65)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        sub_key = ec.generate_private_key(ec.SECP256R1())
        p256dh = base64.urlsafe_b64encode(sub_key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).decode().rstrip("=")
        auth = base64.urlsafe_b64encode(b"\x22" * 16).decode().rstrip("=")
        endpoint = "https://push.services.mozilla.com/push/" + RUN
        r = jpost(stuA, "/api/notifications/push/subscribe", {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, HA)
        check("push subscription stored", r["success"]); sub_id = r["data"]["id"]
        check("invalid push endpoint rejected", stuA.post("/api/notifications/push/subscribe", json={"endpoint": "https://evil.example.com/x", "p256dh": p256dh, "auth": auth}, headers=HA).status_code == 422)
        check("invalid push curve point rejected", stuA.post("/api/notifications/push/subscribe", json={"endpoint": endpoint + "-bad", "p256dh": base64.urlsafe_b64encode(b"\x04" + b"\x11" * 64).decode().rstrip("="), "auth": auth}, headers=HA).status_code == 422)
        check("broad googleapis subdomain rejected", stuA.post("/api/notifications/push/subscribe", json={"endpoint": "https://evil.googleapis.com/x", "p256dh": p256dh, "auth": auth}, headers=HA).status_code == 422)
        check("shared endpoint transfers to current account", jpost(stuB, "/api/notifications/push/subscribe", {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, HB)["success"])
        check("shared endpoint transfers back", jpost(stuA, "/api/notifications/push/subscribe", {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}, HA)["success"])
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-push", "body": "push body", "audience": "user", "user_id": AID}, OH)
        pn = r["data"]["id"]
        calls = []
        def ok_stub(**kwargs):
            calls.append(kwargs)
            class Resp: status_code = 201
            return Resp()
        out = asyncio.run(push_dispatch(ok_stub, (pn, AID)))
        check("push dispatch calls provider stub", len(calls) >= 1 and out["sent"] >= 1)
        check("push provider timeout bounded", all(c.get("timeout") == 5 for c in calls))
        check("push provider redirects disabled", all(getattr(c.get("requests_session"), "max_redirects", None) == 0 for c in calls))
        st = asyncio.run(recipient_status(pn, AID))
        check("push recipient marked sent", st and st[0] == "sent")
        check("push payload has notification URL", any(json.loads(c["data"])["notification_id"] == pn for c in calls))
        # a second subscription that the provider says is gone (410) is removed
        endpoint2 = "https://fcm.googleapis.com/fcm/send/" + RUN
        r = jpost(stuA, "/api/notifications/push/subscribe", {"endpoint": endpoint2, "p256dh": p256dh, "auth": auth}, HA)
        sub2 = r["data"]["id"]
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-push2", "body": "gone", "audience": "user", "user_id": AID}, OH)
        pn2 = r["data"]["id"]
        from pywebpush import WebPushException
        class Gone: status_code = 410
        def gone_stub(**kwargs):
            if kwargs["subscription_info"]["endpoint"] == endpoint2:
                raise WebPushException("gone", response=Gone())
            class Resp: status_code = 201
            return Resp()
        out = asyncio.run(push_dispatch(gone_stub, (pn2, AID)))
        check("expired push subscription removed", out["removed"] >= 1)
        check("failed push does not remove in-app notification", any(n["id"] == pn2 for n in stuA.get("/api/notifications", headers=HA).json()["data"]["rows"]))
        endpoint3 = "https://fcm.googleapis.com/fcm/send/" + RUN + "-partial"
        r = jpost(stuA, "/api/notifications/push/subscribe", {"endpoint": endpoint3, "p256dh": p256dh, "auth": auth}, HA)
        sub3 = r["data"]["id"]
        r = jpost(owner, "/api/admin/notifications", {"title": MARK + "-push3", "body": "partial", "audience": "user", "user_id": AID}, OH)
        pn3 = r["data"]["id"]
        class Flaky: status_code = 500
        def partial_stub(**kwargs):
            if kwargs["subscription_info"]["endpoint"] == endpoint3:
                raise WebPushException("flaky", response=Flaky())
            class Resp: status_code = 201
            return Resp()
        out = asyncio.run(push_dispatch(partial_stub, (pn3, AID)))
        check("partial device failure still delivers sibling", out["sent"] >= 1 and out["failed"] >= 1)
        st = asyncio.run(recipient_status(pn3, AID))
        check("recipient sent when any device succeeds", st and st[0] == "sent")
        check("flaky device retained for retry", stuA.delete(f"/api/notifications/push/{sub3}", headers=HA).status_code == 200)
        cap_ids = []
        for i in range(5):
            rr = jpost(stuB, "/api/notifications/push/subscribe", {"endpoint": f"https://push.services.mozilla.com/push/{RUN}-cap-{i}", "p256dh": p256dh, "auth": auth}, HB)
            cap_ids.append(rr.get("data", {}).get("id"))
        check("five devices allowed", all(cap_ids))
        check("sixth device rejected", stuB.post("/api/notifications/push/subscribe", json={"endpoint": f"https://push.services.mozilla.com/push/{RUN}-cap-6", "p256dh": p256dh, "auth": auth}, headers=HB).status_code == 409)
        check("unsubscribe own device", stuA.delete(f"/api/notifications/push/{sub_id}", headers=HA).status_code == 200)
        check("cannot unsubscribe other device", stuB.delete(f"/api/notifications/push/{sub_id}", headers=HB).status_code in (403, 404))
        check("service worker handles push", "addEventListener(\"push\"" in httpx.get(BASE + "/sw.js").text)
        check("manifest installable", httpx.get(BASE + "/manifest.webmanifest").json()["display"] == "standalone")

        # ---------- scheduled tasks registered ----------
        tasks = owner.get("/api/admin/tasks", headers=OH).json()["data"]["tasks"]
        names = [t["key"] for t in tasks]
        check("friday campaign cron registered", "core.friday_campaign" in names)
        check("push delivery cron registered", "core.push_delivery" in names)
    finally:
        asyncio.run(cleanup(user_ids, course_ids, campaign_ids, stream_ids))
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok]); sys.exit(1)
    print("ALL WAVE-5 CHECKS PASSED")


if __name__ == "__main__":
    main()
