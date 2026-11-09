"""Wave-3 end-to-end verification: forum, chat, files, stickers, moderation.

Runs against the live server + real PostgreSQL. Creates isolated users/course,
then removes its fixtures. Run after tools/migrate_wave3.py and bash run_dev.sh.
"""
from __future__ import annotations
import os, sys, io, re, random, pathlib, asyncio, zipfile, struct
from datetime import timedelta
import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
RESULTS = []
PHONES = []
RUN = str(random.randint(100000, 999999))
WORD = "zzwave3" + RUN
UA = {"User-Agent": "tt-verify-wave3/1.0"}


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def phone():
    p = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    PHONES.append(p)
    return p


def client():
    return httpx.Client(base_url=BASE, headers=UA, timeout=30, follow_redirects=False)


def register(name, division):
    c = client(); p = phone()
    r = c.post("/api/auth/register", json={"phone": p, "password": STUDENT_PASSWORD,
               "name": name, "guardian_phone": phone(), "division_id": division,
               "website": "", "elapsed_ms": 5000}).json()
    if not r.get("success"):
        raise RuntimeError("register failed: " + str(r))
    r = c.post("/api/auth/login", json={"phone": p, "password": STUDENT_PASSWORD}).json()
    return c, {"X-Sesskey": r["data"]["sesskey"]}, r["data"]["user_id"], p


def jpost(c, url, body, headers):
    return c.post(url, json=body, headers=headers).json()


def png_bytes():
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (12, 12), (8, 72, 164)).save(b, format="PNG")
    return b.getvalue()


def mp4_bytes():
    payload = b"x" * 128
    return struct.pack(">I", 20) + b"ftypisom" + struct.pack(">I", 0) + b"isom" + payload


def docx_bytes():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", '<document/>')
    return b.getvalue()


def upload(c, url, data, filename, mime, headers, fields=None):
    files = {"upload": (filename, data, mime)}
    return c.post(url, files=files, data=fields or {}, headers=headers).json()


async def cleanup(course_marker):
    from sqlalchemy import select, delete, or_
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    async with get_sessionmaker()() as db:
        uids = list((await db.execute(select(m.User.id).where(m.User.phone.in_(PHONES)))).scalars().all())
        cid = (await db.execute(select(m.Course.id).where(m.Course.title == course_marker))).scalar_one_or_none()
        cids = [cid] if cid else []
        tids = list((await db.execute(select(m.DiscussionThread.id).where(or_(
            m.DiscussionThread.created_by.in_(uids), m.DiscussionThread.course_id.in_(cids))))).scalars().all()) if uids or cids else []
        chids = list((await db.execute(select(m.Channel.id).where(m.Channel.created_by.in_(uids)))).scalars().all()) if uids else []
        aids = list((await db.execute(select(m.Attachment.id).where(m.Attachment.owner_id.in_(uids)))).scalars().all()) if uids else []
        sids = list((await db.execute(select(m.Sticker.id).where(m.Sticker.owner_id.in_(uids)))).scalars().all()) if uids else []
        eids = list((await db.execute(select(m.Exam.id).where(m.Exam.course_id.in_(cids)))).scalars().all()) if cids else []
        qids = list((await db.execute(select(m.Question.id).where(m.Question.course_id.in_(cids)))).scalars().all()) if cids else []
        mids = list((await db.execute(select(m.ChatMessage.id).where(or_(m.ChatMessage.sender_id.in_(uids), m.ChatMessage.channel_id.in_(chids))))).scalars().all()) if uids or chids else []
        dpids = list((await db.execute(select(m.DiscussionPost.id).where(or_(m.DiscussionPost.user_id.in_(uids), m.DiscussionPost.thread_id.in_(tids))))).scalars().all()) if uids or tids else []
        qpids = list((await db.execute(select(m.QuestionPost.id).where(or_(m.QuestionPost.user_id.in_(uids), m.QuestionPost.question_id.in_(qids))))).scalars().all()) if uids or qids else []
        report_cond = [m.ContentReport.reporter_id.in_(uids)] if uids else []
        if mids: report_cond.append((m.ContentReport.target_type == "chat_message") & m.ContentReport.entity_id.in_(mids))
        if dpids: report_cond.append((m.ContentReport.target_type == "forum_post") & m.ContentReport.entity_id.in_(dpids))
        if qpids: report_cond.append((m.ContentReport.target_type == "question_post") & m.ContentReport.entity_id.in_(qpids))
        if sids: report_cond.append((m.ContentReport.target_type == "sticker") & m.ContentReport.entity_id.in_(sids))
        rids = list((await db.execute(select(m.ContentReport.id).where(or_(*report_cond)))).scalars().all()) if report_cond else []
        attids = list((await db.execute(select(m.ExamAttempt.id).where(or_(
            m.ExamAttempt.user_id.in_(uids), m.ExamAttempt.exam_id.in_(eids))))).scalars().all()) if uids or eids else []
        async def dele(model, cond):
            await db.execute(delete(model).where(cond))
        if uids:
            await dele(m.ForumSubscription, or_(m.ForumSubscription.user_id.in_(uids), m.ForumSubscription.thread_id.in_(tids)))
            await dele(m.DiscussionPost, or_(m.DiscussionPost.user_id.in_(uids), m.DiscussionPost.thread_id.in_(tids)))
            await dele(m.ChatMessage, or_(m.ChatMessage.channel_id.in_(chids), m.ChatMessage.sender_id.in_(uids)))
            await dele(m.DirectContact, or_(m.DirectContact.user_id.in_(uids), m.DirectContact.contact_id.in_(uids), m.DirectContact.channel_id.in_(chids)))
            await dele(m.ChannelMember, or_(m.ChannelMember.user_id.in_(uids), m.ChannelMember.channel_id.in_(chids)))
            await dele(m.ModerationAction, or_(m.ModerationAction.actor_id.in_(uids), m.ModerationAction.target_user_id.in_(uids), m.ModerationAction.report_id.in_(rids)))
            await dele(m.ContentReport, m.ContentReport.id.in_(rids))
            await dele(m.Sticker, m.Sticker.owner_id.in_(uids))
            await dele(m.Attachment, m.Attachment.owner_id.in_(uids))
            await dele(m.UserRestriction, m.UserRestriction.user_id.in_(uids))
            await dele(m.ModerationStrike, m.ModerationStrike.user_id.in_(uids))
            await dele(m.MessageBlock, or_(m.MessageBlock.blocker_id.in_(uids), m.MessageBlock.blocked_id.in_(uids)))
            await dele(m.QuestionPost, or_(m.QuestionPost.user_id.in_(uids), m.QuestionPost.question_id.in_(qids)))
            await dele(m.Session, m.Session.user_id.in_(uids))
            await dele(m.PasswordHistory, m.PasswordHistory.user_id.in_(uids))
            await dele(m.PasswordResetToken, m.PasswordResetToken.user_id.in_(uids))
            await dele(m.LoginAttempt, m.LoginAttempt.phone.in_(PHONES))
            await dele(m.AuditLog, m.AuditLog.actor_id.in_(uids))
        if rids:
            await dele(m.ModerationAction, m.ModerationAction.report_id.in_(rids))
            await dele(m.ContentReport, m.ContentReport.id.in_(rids))
        if tids:
            await dele(m.DiscussionThread, m.DiscussionThread.id.in_(tids))
        if chids:
            await dele(m.Channel, m.Channel.id.in_(chids))
        if attids:
            await dele(m.AttemptAnswer, m.AttemptAnswer.attempt_id.in_(attids))
        if uids or eids:
            await dele(m.ExamAttempt, or_(m.ExamAttempt.user_id.in_(uids), m.ExamAttempt.exam_id.in_(eids)))
        if eids:
            await dele(m.ExamQuestion, m.ExamQuestion.exam_id.in_(eids))
            await dele(m.Exam, m.Exam.id.in_(eids))
        if qids:
            await dele(m.Question, m.Question.id.in_(qids))
        if cids:
            await dele(m.CourseStudent, m.CourseStudent.course_id.in_(cids))
            await dele(m.Course, m.Course.id.in_(cids))
        await dele(m.ProfanityWord, m.ProfanityWord.word == WORD)
        if uids:
            await dele(m.User, m.User.id.in_(uids))
        await db.commit()
    await dispose_db()


def main():
    print("== Taleb Talta Wave-3 verification ==")
    course_marker = "كورس اختبار التواصل " + RUN
    owner = client()
    r = owner.post("/api/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD}).json()
    check("owner login", r.get("success")); OH = {"X-Sesskey": r["data"]["sesskey"]}
    anon = client()
    check("anonymous forum API rejected", anon.get("/api/forum/threads").status_code == 401)
    check("anonymous chat API rejected", anon.get("/api/chat/channels").status_code == 401)
    try:
        r = jpost(owner, "/api/courses", {"title": course_marker, "division_id": 1, "visibility": "visible"}, OH)
        check("create isolated course", r.get("success")); cid = r["data"]["id"]
        A, AH, aid, ap = register("طالب تواصل أ", 1)
        B, BH, bid, bp = register("طالب تواصل ب", 1)
        C, CH, cuid, cp = register("طالب تواصل ج", 2)
        D, DH, did, dp = register("طالب مخالفات", 1)
        for c, h in ((A, AH), (B, BH), (D, DH)):
            check("enrol fixture student", jpost(c, f"/api/courses/{cid}/enrol", {}, h).get("success"))
        check("student moderation page gated", C.get("/admin/moderation").status_code in (303, 403))
        check("forum page renders disclaimer", "مسؤولية صاحبها" in A.get("/forum").text)
        check("chat page renders disclaimer", "مسؤولية صاحبها" in A.get("/chat").text)
        check("moderation page renders", "لوحة الإشراف" in owner.get("/admin/moderation").text)

        # ---- forum ----
        r = jpost(A, "/api/forum/threads", {"title": "موضوع اختبار " + RUN, "body": "نذاكر مع بعض؟"}, AH)
        check("create general thread", r.get("success")); tid = r["data"]["id"]
        det = A.get(f"/api/forum/threads/{tid}").json()
        first_post = det["data"]["posts"][0]["id"]
        r = jpost(B, f"/api/forum/threads/{tid}/posts", {"body": "أنا معاك", "parent_id": first_post}, BH)
        check("nested reply", r.get("success")); reply_id = r["data"]["id"]
        det = B.get(f"/api/forum/threads/{tid}").json()
        check("reply keeps parent reference", any(p["id"] == reply_id and p["parent_id"] == first_post for p in det["data"]["posts"]))
        check("author auto-subscribed", det["data"]["subscribed"] or A.get(f"/api/forum/threads/{tid}").json()["data"]["subscribed"])
        r = jpost(B, f"/api/forum/threads/{tid}/subscribe", {}, BH)
        check("subscribe toggle", r.get("success"))
        jpost(A, f"/api/forum/threads/{tid}/posts", {"body": "رد جديد للقراءة"}, AH)
        before = B.get(f"/api/forum/threads/{tid}").json()["data"]["unread"]
        check("unread count before read", before >= 1)
        again = B.get(f"/api/forum/threads/{tid}").json()["data"]["unread"]
        check("GET thread does not mark read", again == before)
        jpost(B, f"/api/forum/threads/{tid}/read", {}, BH)
        after = B.get(f"/api/forum/threads/{tid}").json()["data"]["unread"]
        check("explicit read clears unread", after == 0)
        r = jpost(owner, f"/api/forum/threads/{tid}/lock", {"locked": True}, OH)
        check("staff locks thread", r.get("success"))
        r = A.post(f"/api/forum/threads/{tid}/posts", json={"body": "محاولة رد"}, headers=AH)
        check("locked thread rejects student reply", r.status_code == 403)
        jpost(owner, f"/api/forum/threads/{tid}/lock", {"locked": False}, OH)
        r = jpost(A, "/api/forum/threads", {"title": "موضوع الكورس", "body": "للمسجلين فقط", "course_id": cid}, AH)
        check("create course thread", r.get("success")); ctid = r["data"]["id"]
        check("unenrolled student cannot read course thread", C.get(f"/api/forum/threads/{ctid}").status_code == 404)
        r = C.post("/api/forum/threads", json={"title": "x", "body": "x", "course_id": cid}, headers=CH)
        check("unenrolled student cannot create course thread", r.status_code == 403)
        r = A.post(f"/api/forum/threads/{tid}/posts", json={"body": "x"})
        check("missing sesskey rejected", r.status_code == 403)

        # ---- question deep link ----
        r = jpost(owner, "/api/questions", {"course_id": cid, "qtype": "mcq_single", "prompt": "سؤال المناقشة",
                  "options_json": ["أ", "ب"], "answer_json": {"correct": 0}}, OH)
        qid = r["data"]["id"]
        r = jpost(owner, "/api/exams", {"course_id": cid, "title": "امتحان المناقشة", "max_attempts": 0}, OH)
        eid = r["data"]["id"]
        jpost(owner, f"/api/exams/{eid}/questions", {"question_id": qid}, OH)
        r = B.post(f"/api/forum/question/{qid}", json={}, headers=BH)
        check("question discussion requires submitted attempt", r.status_code == 403)
        r = jpost(A, f"/api/exams/{eid}/start", {}, AH); att = r["data"]["attempt_id"]
        jpost(A, f"/api/attempts/{att}/submit", {"answers": {str(qid): {"choice": 0}}}, AH)
        r = jpost(A, f"/api/forum/question/{qid}", {"attempt_id": att}, AH)
        check("submitted student opens question thread", r.get("success")); qtid = r["data"]["id"]
        check("question thread carries exam reference", A.get(f"/api/forum/threads/{qtid}").json()["data"]["exam_id"] == eid)

        # ---- private messages / contacts / read / block ----
        r = jpost(A, "/api/messages/find", {}, AH) if False else A.get(f"/api/messages/find?phone={bp}").json()
        check("exact phone contact discovery", r.get("success") and r["data"]["user_id"] == bid)
        r = jpost(A, "/api/messages/start", {"user_id": bid}, AH)
        check("start private conversation", r.get("success")); priv = r["data"]["channel_id"]
        r = jpost(A, f"/api/chat/channels/{priv}/messages", {"body": "أهلا يا زميل"}, AH)
        check("send private message", r.get("success")); m1 = r["data"]["message"]["id"]
        hist = B.get(f"/api/chat/channels/{priv}/messages").json()
        check("recipient sees unread private message", hist["data"]["channel"]["unread"] == 1)
        jpost(B, f"/api/chat/channels/{priv}/read", {"message_id": m1}, BH)
        check("read state clears unread", B.get(f"/api/chat/channels/{priv}/messages").json()["data"]["channel"]["unread"] == 0)
        r = jpost(A, f"/api/chat/channels/{priv}/messages", {"body": "رسالة تانية"}, AH)
        m2 = r["data"]["message"]["id"]
        poll = B.get(f"/api/chat/channels/{priv}/messages?after_id={m1}").json()
        check("cursor polling returns only newer messages", [x["id"] for x in poll["data"]["messages"]] == [m2])
        contacts = A.get("/api/messages/contacts").json()
        check("contact list saved", any(c["user_id"] == bid for c in contacts["data"]))
        check("outsider cannot read private history", C.get(f"/api/chat/channels/{priv}/messages").status_code == 403)
        check("outsider cannot send to private channel", C.post(f"/api/chat/channels/{priv}/messages", json={"body": "x"}, headers=CH).status_code == 403)
        jpost(A, "/api/messages/block", {"user_id": bid}, AH)
        check("block stops sender", A.post(f"/api/chat/channels/{priv}/messages", json={"body": "x"}, headers=AH).status_code == 403)
        check("block stops recipient too", B.post(f"/api/chat/channels/{priv}/messages", json={"body": "x"}, headers=BH).status_code == 403)
        jpost(A, "/api/messages/unblock", {"user_id": bid}, AH)
        r = jpost(A, f"/api/chat/channels/{priv}/messages", {"body": "Hello WORLD"}, AH)
        check("unblock restores messaging", r.get("success"))
        check("clean text preserves casing", r.get("data", {}).get("message", {}).get("body") == "Hello WORLD")

        # ---- group + division channels ----
        r = jpost(A, "/api/chat/groups", {"title": "مجموعة اختبار " + RUN, "member_ids": [bid]}, AH)
        check("create group channel", r.get("success")); gid = r["data"]["channel_id"]
        check("group message", jpost(A, f"/api/chat/channels/{gid}/messages", {"body": "رسالة المجموعة"}, AH).get("success"))
        r = A.post(f"/api/chat/channels/{gid}/members", json={"user_ids": [cuid]}, headers=AH)
        check("cannot add unrelated division student to group", r.status_code == 403)
        chans = A.get("/api/chat/channels").json()["data"]
        div1 = next(c for c in chans if c["kind"] == "division" and c["division_id"] == 1)
        check("division channel auto-membered", div1["id"] > 0)
        check("other division cannot read channel", C.get(f"/api/chat/channels/{div1['id']}/messages").status_code == 403)
        check("division channel message", jpost(A, f"/api/chat/channels/{div1['id']}/messages", {"body": "يا أهل الشعبة"}, AH).get("success"))
        dmsg = jpost(D, f"/api/chat/channels/{div1['id']}/messages", {"body": "رسالة نظيفة للمراجعة"}, DH)["data"]["message"]["id"]

        # ---- attachments + quota + range + safe download ----
        r = upload(A, "/api/chat/attachments", png_bytes(), "study.png", "image/png", AH)
        check("upload verified image", r.get("success")); img = r["data"]
        r = jpost(A, f"/api/chat/channels/{priv}/messages", {"body": "صورة للمذاكرة", "attachment_id": img["id"]}, AH)
        check("send image attachment", r.get("success"))
        fr = B.get(img["url"])
        check("member downloads private image", fr.status_code == 200 and fr.content == png_bytes())
        check("private gateway headers", fr.headers.get("cache-control") == "private, no-store" and fr.headers.get("x-content-type-options") == "nosniff")
        check("outsider denied attachment", C.get(img["url"]).status_code == 403)
        r = upload(A, "/api/chat/attachments", b"not a png", "fake.png", "image/png", AH)
        check("disguised image rejected", not r.get("success"))
        async def quota_test():
            from sqlalchemy import select, update
            from app.core.db import get_sessionmaker, dispose_db
            from app.models import Attachment
            from app import config
            async with get_sessionmaker()() as db:
                a = (await db.execute(select(Attachment).where(Attachment.id == img["id"]))).scalar_one()
                old = a.file_size
                a.file_size = config.CHAT_UPLOAD_QUOTA_BYTES
                await db.commit()
            await dispose_db()
            return old
        old_size = asyncio.run(quota_test())
        r = upload(A, "/api/chat/attachments", png_bytes(), "second.png", "image/png", AH)
        check("upload quota enforced", not r.get("success") and "100" in r.get("message", ""), str(r))
        async def restore():
            from sqlalchemy import update
            from app.core.db import get_sessionmaker, dispose_db
            from app.models import Attachment
            async with get_sessionmaker()() as db:
                await db.execute(update(Attachment).where(Attachment.id == img["id"]).values(file_size=old_size))
                await db.commit()
            await dispose_db()
        asyncio.run(restore())
        r = upload(A, "/api/chat/attachments", mp4_bytes(), "lesson.mp4", "video/mp4", AH)
        check("upload mp4 container", r.get("success")); vid = r["data"]
        jpost(A, f"/api/chat/channels/{priv}/messages", {"attachment_id": vid["id"]}, AH)
        rr = B.get(vid["url"], headers={"Range": "bytes=0-3"})
        check("video range request supported", rr.status_code == 206 and len(rr.content) == 4)
        r = upload(A, "/api/chat/attachments", docx_bytes(), "notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", AH)
        check("upload OOXML study resource", r.get("success")); doc = r["data"]
        jpost(A, f"/api/chat/channels/{priv}/messages", {"attachment_id": doc["id"]}, AH)
        dr = B.get(doc["url"])
        check("document forced attachment download", dr.status_code == 200 and "attachment" in dr.headers.get("content-disposition", "") and dr.headers.get("content-type") == "application/octet-stream")

        # ---- stickers ----
        r = upload(A, "/api/stickers", png_bytes(), "sticker.png", "image/png", AH, {"title": "ستيكر اختبار"})
        check("submit custom sticker", r.get("success")); sid = r["data"]["id"]
        check("pending sticker hidden from others", C.get(f"/api/stickers/{sid}/file").status_code == 403)
        check("owner can preview pending sticker", A.get(f"/api/stickers/{sid}/file").status_code == 200)
        check("student cannot approve sticker", A.post(f"/api/stickers/{sid}/approve", json={"reason": ""}, headers=AH).status_code == 403)
        check("owner approves sticker", jpost(owner, f"/api/stickers/{sid}/approve", {"reason": ""}, OH).get("success"))
        approved = B.get("/api/stickers").json()["data"]
        check("approved sticker listed", any(s["id"] == sid for s in approved))
        r = jpost(A, f"/api/chat/channels/{priv}/messages", {"sticker_id": sid}, AH)
        check("send approved sticker", r.get("success") and r["data"]["message"]["sticker"]["id"] == sid)
        r = upload(A, "/api/stickers", png_bytes(), "sticker2.png", "image/png", AH, {"title": "ستيكر مرفوض"})
        sid2 = r["data"]["id"]
        check("owner rejects sticker with reason", jpost(owner, f"/api/stickers/{sid2}/reject", {"reason": "مش مناسب"}, OH).get("success"))
        check("rejected sticker cannot be sent", A.post(f"/api/chat/channels/{priv}/messages", json={"sticker_id": sid2}, headers=AH).status_code == 403)

        # ---- profanity escalation + scoped ban ----
        check("admin adds dictionary word", jpost(owner, "/api/moderation/profanity", {"word": WORD, "enabled": True}, OH).get("success"))
        r = jpost(D, f"/api/forum/threads/{tid}/posts", {"body": WORD + " " + WORD}, DH)
        check("one submission counts one warning", r.get("success") and r.get("message", "").startswith("تنبيه أول"))
        det = D.get(f"/api/forum/threads/{tid}").json()
        check("profanity masked before storage", any("*" in p["body"] and WORD not in p["body"] for p in det["data"]["posts"]))
        r = jpost(D, f"/api/chat/channels/{div1['id']}/messages", {"body": WORD}, DH)
        check("second warning across chat/forum", r.get("success") and r.get("message", "").startswith("تنبيه تاني"))
        r = D.post(f"/api/chat/channels/{div1['id']}/messages", json={"body": WORD}, headers=DH)
        check("third strike bans chat/evaluations", r.status_code == 403 and "30" in r.json().get("message", ""))
        check("ban revokes existing sessions", D.get("/api/chat/channels").status_code == 401)
        r = D.post("/api/auth/login", json={"phone": dp, "password": STUDENT_PASSWORD}).json()
        check("restricted user can still log in for courses", r.get("success")); DH = {"X-Sesskey": r["data"]["sesskey"]}
        me = D.get("/api/auth/me").json()["data"]
        check("me exposes scoped restriction", me.get("restricted") is True)
        check("course access preserved under scoped ban", any(c["id"] == cid for c in D.get("/api/courses").json()["data"]))
        r = D.post(f"/api/exams/{eid}/start", json={}, headers=DH)
        check("evaluations blocked under scoped ban", r.status_code == 403 and "التقييمات" in r.json().get("message", ""))
        check("forum blocked under scoped ban", D.post(f"/api/forum/threads/{tid}/posts", json={"body": "x"}, headers=DH).status_code == 403)
        ov = owner.get("/api/moderation/overview").json()["data"]
        check("admin alerted on restricted login", any(a["user_id"] == did for a in ov["alerts"]))
        restriction = next(x for x in ov["restrictions"] if x["user_id"] == did)
        check("restriction lists scoped ban", restriction["scope"] == "chat_evaluations")
        check("owner lifts restriction", jpost(owner, "/api/moderation/restrictions/lift", {"restriction_id": restriction["id"], "reason": "اختبار فك القيد"}, OH).get("success"))
        check("chat works after lift", jpost(D, f"/api/chat/channels/{div1['id']}/messages", {"body": "تمام"}, DH).get("success"))
        check("admin disables dictionary word", jpost(owner, "/api/moderation/profanity", {"word": WORD, "enabled": False}, OH).get("success"))
        r = jpost(D, f"/api/chat/channels/{div1['id']}/messages", {"body": WORD}, DH)
        check("disabled word no longer filtered", r.get("success") and WORD in r["data"]["message"]["body"])

        # ---- reports + moderation decisions ----
        r = jpost(B, "/api/moderation/reports", {"entity_type": "forum_post", "entity_id": first_post, "reason": "محتوى غير مناسب"}, BH)
        check("report forum post", r.get("success")); report_id = r["data"]["id"]
        r = jpost(B, "/api/moderation/reports", {"entity_type": "forum_post", "entity_id": first_post, "reason": "مرة تانية"}, BH)
        check("duplicate report rejected", not r.get("success"))
        queue = owner.get("/api/moderation/reports?status=pending").json()["data"]
        check("moderation queue shows snapshot", any(x["id"] == report_id and x["snapshot"] for x in queue))
        check("student cannot read moderation queue", A.get("/api/moderation/reports").status_code == 403)
        check("staff removes reported content", jpost(owner, f"/api/moderation/reports/{report_id}/decide", {"action": "remove", "reason": "مخالفة"}, OH).get("success"))
        det = A.get(f"/api/forum/threads/{tid}").json()
        check("removed post hidden from thread", all(p["id"] != first_post for p in det["data"]["posts"]))
        r = jpost(owner, "/api/moderation/reports", {"entity_type": "chat_message", "entity_id": dmsg, "reason": "مراجعة يدوية"}, OH)
        check("staff can report chat message", r.get("success")); rid2 = r["data"]["id"]
        check("manual report ban", jpost(owner, f"/api/moderation/reports/{rid2}/decide", {"action": "ban", "reason": "قرار إشراف"}, OH).get("success"))
        ov = owner.get("/api/moderation/overview").json()["data"]
        restriction = next(x for x in ov["restrictions"] if x["user_id"] == did)
        check("manual ban creates restriction", restriction["id"] > 0)
        jpost(owner, "/api/moderation/restrictions/lift", {"restriction_id": restriction["id"], "reason": "انتهى الاختبار"}, OH)
        r = jpost(B, "/api/moderation/reports", {"entity_type": "chat_message", "entity_id": m2, "reason": "تنبيه يدوي"}, BH)
        rid3 = r["data"]["id"]
        check("manual warning decision", jpost(owner, f"/api/moderation/reports/{rid3}/decide", {"action": "warn", "reason": "خلي بالك"}, OH).get("success"))
        async def warn_check():
            from sqlalchemy import select
            from app.core.db import get_sessionmaker, dispose_db
            from app.models import ModerationStrike, ModerationAction
            async with get_sessionmaker()() as db:
                count = (await db.execute(select(ModerationStrike.count).where(ModerationStrike.user_id == aid))).scalar_one_or_none()
                linked = (await db.execute(select(ModerationAction.id).where(ModerationAction.report_id == rid3, ModerationAction.decision == "warn"))).first()
            await dispose_db()
            return count, linked is not None
        count, linked = asyncio.run(warn_check())
        check("manual warning increments strike once", count == 1)
        check("manual warning linked to report", linked)
        r = jpost(B, "/api/moderation/reports", {"entity_type": "chat_message", "entity_id": m1, "reason": "سليم"}, BH)
        rid4 = r["data"]["id"]
        check("approve/dismiss report", jpost(owner, f"/api/moderation/reports/{rid4}/decide", {"action": "approve", "reason": ""}, OH).get("success"))
        check("question discussion post works", jpost(A, f"/api/questions/{qid}/posts", {"body": "ليه الإجابة أ؟"}, AH).get("success"))
    finally:
        asyncio.run(cleanup(course_marker))
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok]); sys.exit(1)
    print("ALL WAVE-3 CHECKS PASSED")


if __name__ == "__main__":
    main()
