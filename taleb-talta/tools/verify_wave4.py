"""Wave-4 end-to-end verification: administration, builders, reports, cron, backups.

Live server + real PostgreSQL. Creates isolated fixtures and removes them.
Run after tools/migrate_wave4.py and bash run_dev.sh (plus python -m app.cron).
"""
from __future__ import annotations
import os, sys, io, re, random, pathlib, asyncio, time, tarfile, subprocess, hashlib
from datetime import timedelta, date
import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
RESULTS, PHONES = [], []
RUN = str(random.randint(100000, 999999))
MARK = "zzwave4-" + RUN
UA = {"User-Agent": "tt-verify-wave4/1.0"}
START = None


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def phone():
    p = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    PHONES.append(p)
    return p


def client():
    return httpx.Client(base_url=BASE, headers=UA, timeout=120, follow_redirects=False)


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


def png_bytes():
    from PIL import Image
    b = io.BytesIO(); Image.new("RGB", (24, 24), (8, 72, 164)).save(b, format="PNG")
    return b.getvalue()


async def db_role(p, role):
    from sqlalchemy import select, update
    from app.core.db import get_sessionmaker, dispose_db
    from app.models import User
    async with get_sessionmaker()() as db:
        await db.execute(update(User).where(User.phone == p).values(role=role))
        await db.commit()
    await dispose_db()


async def db_query(fn):
    from app.core.db import get_sessionmaker, dispose_db
    async with get_sessionmaker()() as db:
        out = await fn(db)
    await dispose_db()
    return out


async def cleanup():
    from sqlalchemy import select, delete, or_
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    from app import config
    async with get_sessionmaker()() as db:
        # The zzwave4- namespace is reserved for this suite. Include interrupted
        # prior runs so a failed assertion never leaves staff accounts behind.
        fixture_users = (await db.execute(select(m.User).where(m.User.name.like("zzwave4-%")))).scalars().all()
        uids = [u.id for u in fixture_users]
        fixture_phones = list(set(PHONES + [u.phone for u in fixture_users]))
        cids = list((await db.execute(select(m.Course.id).where(m.Course.title.like("zzwave4-%")))).scalars().all())
        fids = list((await db.execute(select(m.CustomField.id).where(m.CustomField.machine_name.like("w4\\_%", escape="\\")))).scalars().all())
        eids = list((await db.execute(select(m.Exam.id).where(m.Exam.course_id.in_(cids)))).scalars().all()) if cids else []
        aids = list((await db.execute(select(m.ExamAttempt.id).where(m.ExamAttempt.exam_id.in_(eids)))).scalars().all()) if eids else []
        bids = list((await db.execute(select(m.BackupArtifact.id).where(m.BackupArtifact.created_at >= START))).scalars().all()) if START else []
        async def dele(model, cond):
            await db.execute(delete(model).where(cond))
        if bids:
            rows = (await db.execute(select(m.BackupArtifact).where(m.BackupArtifact.id.in_(bids)))).scalars().all()
            for row in rows:
                (config.BACKUP_DIR / row.file_name).unlink(missing_ok=True)
            await dele(m.BackupArtifact, m.BackupArtifact.id.in_(bids))
        if fids:
            await dele(m.CustomFieldValue, m.CustomFieldValue.field_id.in_(fids))
            await dele(m.CustomField, m.CustomField.id.in_(fids))
        if cids:
            await dele(m.CustomFieldValue, (m.CustomFieldValue.entity_id.in_(cids)) & (m.CustomFieldValue.field_id.in_(select(m.CustomField.id).where(m.CustomField.applies_to == "course"))))
        if uids:
            await dele(m.CustomFieldValue, (m.CustomFieldValue.entity_id.in_(uids)) & (m.CustomFieldValue.field_id.in_(select(m.CustomField.id).where(m.CustomField.applies_to == "user"))))
            await dele(m.DashboardPreference, m.DashboardPreference.user_id.in_(uids))
            await dele(m.DigestDelivery, m.DigestDelivery.user_id.in_(uids))
            await dele(m.ForumSubscription, m.ForumSubscription.user_id.in_(uids))
            await dele(m.ChannelMember, m.ChannelMember.user_id.in_(uids))
            await dele(m.DirectContact, or_(m.DirectContact.user_id.in_(uids), m.DirectContact.contact_id.in_(uids)))
            await dele(m.UserRestriction, m.UserRestriction.user_id.in_(uids))
            await dele(m.ModerationStrike, m.ModerationStrike.user_id.in_(uids))
            await dele(m.PasswordHistory, m.PasswordHistory.user_id.in_(uids))
            await dele(m.Session, m.Session.user_id.in_(uids))
            await dele(m.LoginAttempt, m.LoginAttempt.phone.in_(fixture_phones))
            await dele(m.PasswordResetToken, m.PasswordResetToken.user_id.in_(uids))
            await dele(m.CourseStudent, m.CourseStudent.user_id.in_(uids))
            await dele(m.LessonProgress, m.LessonProgress.user_id.in_(uids))
        if aids:
            await dele(m.AttemptAnswer, m.AttemptAnswer.attempt_id.in_(aids))
            await dele(m.ExamAttempt, m.ExamAttempt.id.in_(aids))
        if eids:
            await dele(m.ExamQuestion, m.ExamQuestion.exam_id.in_(eids))
            await dele(m.Question, m.Question.course_id.in_(cids))
            await dele(m.Exam, m.Exam.id.in_(eids))
        if cids:
            await dele(m.CourseStudent, m.CourseStudent.course_id.in_(cids))
            await dele(m.LessonProgress, m.LessonProgress.lesson_id.in_(select(m.Lesson.id).join(m.CourseSection, m.CourseSection.id == m.Lesson.section_id).where(m.CourseSection.course_id.in_(cids))))
            await dele(m.LessonItem, m.LessonItem.lesson_id.in_(select(m.Lesson.id).join(m.CourseSection, m.CourseSection.id == m.Lesson.section_id).where(m.CourseSection.course_id.in_(cids))))
            await dele(m.Lesson, m.Lesson.section_id.in_(select(m.CourseSection.id).where(m.CourseSection.course_id.in_(cids))))
            await dele(m.CourseSection, m.CourseSection.course_id.in_(cids))
            await dele(m.Course, m.Course.id.in_(cids))
        await dele(m.TaskRun, m.TaskRun.task_key == "core.invalid")
        await dele(m.ScheduledTask, m.ScheduledTask.classname == "core.invalid")
        await dele(m.ChatMessage, m.ChatMessage.body.like("zzwave4-%-ref"))
        await dele(m.Sticker, m.Sticker.title.like("zzwave4-%-sticker"))
        await dele(m.Attachment, m.Attachment.file_path.like("zzwave4-%"))
        await dele(m.MenuItem, m.MenuItem.label.like("zzwave4-%-menu"))
        presets = list((await db.execute(select(m.ThemePreset).where(m.ThemePreset.name.like("zzwave4-%-theme")))).scalars().all())
        for preset in presets:
            await dele(m.RoleTheme, m.RoleTheme.theme_key == f"preset-{preset.id}")
            await db.delete(preset)
        divs = list((await db.execute(select(m.Division).where(m.Division.name.like("zzwave4-%")))).scalars().all())
        for div in divs:
            ch = (await db.execute(select(m.Channel).where(m.Channel.division_id == div.id))).scalar_one_or_none()
            if ch:
                await dele(m.ChannelMember, m.ChannelMember.channel_id == ch.id)
                await dele(m.DirectContact, m.DirectContact.channel_id == ch.id)
                await db.delete(ch)
            await db.delete(div)
        logo = (await db.execute(select(m.SiteSetting).where(m.SiteSetting.key == "site.logo_path"))).scalar_one_or_none()
        if logo and logo.value.startswith("branding/"):
            from app.core import files
            files.delete(logo.value)
            await db.delete(logo)
        for key in ("site.name", "site.contact_phone", "site.contact_message"):
            await dele(m.SiteSetting, m.SiteSetting.key == key)
        await db.execute(delete(m.RateLimit))
        await db.commit()
    await dispose_db()


async def seed_attempt(course_id, user_id):
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    async with get_sessionmaker()() as db:
        exam = m.Exam(course_id=course_id, title=MARK + "-exam", visibility="visible", created_by=user_id)
        db.add(exam); await db.flush()
        now = m.utcnow()
        db.add(m.ExamAttempt(exam_id=exam.id, user_id=user_id, attempt_number=1, status="graded", score=8, max_score=10,
                             started_at=now - timedelta(minutes=5), submitted_at=now, graded_at=now))
        db.add(m.ExamAttempt(exam_id=exam.id, user_id=user_id, attempt_number=2, status="graded", score=6, max_score=10,
                             started_at=now - timedelta(minutes=15), submitted_at=now - timedelta(minutes=10), graded_at=now))
        await db.commit(); eid = exam.id
    await dispose_db()
    return eid


async def expire_session(p):
    from sqlalchemy import update
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    async with get_sessionmaker()() as db:
        uid = (await db.execute(__import__("sqlalchemy").select(m.User.id).where(m.User.phone == p))).scalar_one()
        await db.execute(update(m.Session).where(m.Session.user_id == uid).values(last_seen=m.utcnow() - timedelta(minutes=6)))
        await db.commit()
    await dispose_db()


async def set_task_due(key):
    from sqlalchemy import select, update
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    async with get_sessionmaker()() as db:
        await db.execute(update(m.ScheduledTask).where(m.ScheduledTask.classname == key).values(next_run=m.utcnow() - timedelta(minutes=1)))
        maxid = (await db.execute(select(__import__("sqlalchemy").func.max(m.TaskRun.id)))).scalar_one() or 0
        await db.commit()
    await dispose_db()
    return maxid


async def wait_worker(key, maxid):
    from sqlalchemy import select
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    deadline = time.monotonic() + 75
    while time.monotonic() < deadline:
        async with get_sessionmaker()() as db:
            row = (await db.execute(select(m.TaskRun).where(m.TaskRun.id > maxid, m.TaskRun.task_key == key,
                   m.TaskRun.triggered_by.is_(None), m.TaskRun.status == "success"))).scalar_one_or_none()
        await dispose_db()
        if row:
            return True
        time.sleep(3)
    return False


async def wait_unlock(task_id):
    from sqlalchemy import select
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        async with get_sessionmaker()() as db:
            task = (await db.execute(select(m.ScheduledTask).where(m.ScheduledTask.id == task_id))).scalar_one()
            locked = bool(task.locked_until and task.locked_until > m.utcnow())
        await dispose_db()
        if not locked:
            return True
        time.sleep(1)
    return False


async def lock_task(task_id, locked):
    from sqlalchemy import update
    from app.core.db import get_sessionmaker, dispose_db
    from app import models as m
    async with get_sessionmaker()() as db:
        await db.execute(update(m.ScheduledTask).where(m.ScheduledTask.id == task_id).values(
            locked_until=m.utcnow() + timedelta(minutes=5) if locked else None, lock_token="test" if locked else ""))
        await db.commit()
    await dispose_db()


async def cron_regressions(student_id):
    """Exercise rollback/history and attachment-reference cleanup on real PG."""
    from sqlalchemy import select, delete
    from app.core.db import get_sessionmaker, dispose_db
    from app.core import cron
    from app import models as m
    try:
        async with get_sessionmaker()() as db:
            task = m.ScheduledTask(classname="core.invalid", minute="*", hour="*", day="*",
                                   month="*", dayofweek="*", enabled=True)
            db.add(task); await db.commit(); await db.refresh(task)
            token = await cron._claim(db, task, manual=True)
            run = await cron.execute(db, task, token, manual=True)
            check("failed task history survives rollback", run.status == "failed" and run.error_key == "cron.unknown_task")
            fresh = (await db.execute(select(m.ScheduledTask).where(m.ScheduledTask.id == task.id))).scalar_one()
            check("failed task releases its lock", not fresh.lock_token and fresh.locked_until is None)
            await db.execute(delete(m.TaskRun).where(m.TaskRun.task_id == task.id))
            await db.delete(task); await db.commit()
            old = m.utcnow() - timedelta(days=2)
            channel_id = (await db.execute(select(m.Channel.id).where(m.Channel.kind == "division").limit(1))).scalar_one()
            orphan = m.Attachment(owner_id=student_id, purpose="chat", file_path=f"zzwave4-orphan-{RUN}.txt",
                                  file_name="orphan.txt", file_size=0, mime="text/plain", sha256="0" * 64, created_at=old)
            used_msg = m.Attachment(owner_id=student_id, purpose="chat", file_path=f"zzwave4-message-{RUN}.txt",
                                    file_name="message.txt", file_size=0, mime="text/plain", sha256="0" * 64, created_at=old)
            used_sticker = m.Attachment(owner_id=student_id, purpose="sticker", file_path=f"zzwave4-sticker-{RUN}.png",
                                        file_name="sticker.png", file_size=0, mime="image/png", sha256="0" * 64, created_at=old)
            db.add_all([orphan, used_msg, used_sticker]); await db.commit()
            for a in (orphan, used_msg, used_sticker): await db.refresh(a)
            message = m.ChatMessage(channel_id=channel_id, sender_id=student_id, body=MARK + "-ref", attachment_id=used_msg.id)
            sticker = m.Sticker(owner_id=student_id, attachment_id=used_sticker.id, title=MARK + "-sticker")
            db.add_all([message, sticker]); await db.commit()
            ids = [orphan.id, used_msg.id, used_sticker.id]
            counts = await cron._cleanup(db, None)
            remaining = set((await db.execute(select(m.Attachment.id).where(m.Attachment.id.in_(ids)))).scalars().all())
            check("cleanup removes only unreferenced old attachments", counts["attachments"] >= 1 and orphan.id not in remaining)
            check("cleanup preserves message and sticker attachments", used_msg.id in remaining and used_sticker.id in remaining)
            await db.execute(delete(m.ChatMessage).where(m.ChatMessage.attachment_id == used_msg.id))
            await db.execute(delete(m.Sticker).where(m.Sticker.attachment_id == used_sticker.id))
            await db.execute(delete(m.Attachment).where(m.Attachment.id.in_(ids)))
            await db.commit()
    finally:
        await dispose_db()

def main():
    global START, AH, A, AID, AP
    from app.models import utcnow
    START = utcnow()
    owner = client(); OH, OID = login(owner, OWNER_PHONE, OWNER_PASSWORD)
    A, AH, AID, AP = register(MARK + "-student")
    B, BH, BID, BP = register(MARK + "-student2")
    T, TH, TID, TP = register(MARK + "-teacher")
    ADM, ADMH, ADMID, ADMP = register(MARK + "-admin")
    MOD, MODH, MODID, MODP = register(MARK + "-moderator")
    course_id = other_course = field_ids = []
    preset_id = menu_id = division_id = backup_id = 0
    try:
        # ---- capabilities / CSRF ----
        check("owner login", OID > 0)
        check("student cannot read settings", A.get("/api/admin/settings").status_code == 403)
        check("student cannot list users", A.get("/api/admin/users").status_code == 403)
        check("settings write requires CSRF", owner.post("/api/admin/settings", json={"values": {"site.name": "x"}}).status_code == 403)
        check("student cannot run cron", A.post("/api/cron/run").status_code == 403)
        # ---- typed settings / branding ----
        settings = owner.get("/api/admin/settings").json()["data"]
        check("settings tree exposes typed specs", settings["specs"]["site.registration_enabled"]["type"] == "bool")
        r = jpost(owner, "/api/admin/settings", {"values": {"site.name": MARK + "-site", "site.contact_phone": "01000000001", "site.contact_message": "تواصل معنا", "site.registration_enabled": True, "site.maintenance": False}}, OH)
        check("general settings save", r.get("success"))
        check("manifest uses saved site name", owner.get("/manifest.webmanifest").json()["name"] == MARK + "-site")
        r = owner.post("/api/admin/logo", files={"file": ("logo.png", png_bytes(), "image/png")}, headers=OH)
        check("logo upload validates and stores", r.status_code == 200 and r.json().get("success"), r.text[:100])
        logo = owner.get("/branding/logo")
        check("branding logo served as image", logo.status_code == 200 and logo.headers["content-type"].startswith("image/"))
        r = owner.post("/api/admin/logo", files={"file": ("logo.txt", b"not an image", "text/plain")}, headers=OH)
        check("non-image logo rejected", r.status_code == 422)
        r = jpost(owner, "/api/admin/settings", {"values": {"site.registration_enabled": False}}, OH)
        closed = client().post("/api/auth/register", json={"phone": phone(), "password": STUDENT_PASSWORD, "name": "closed", "guardian_phone": phone(), "division_id": 1, "website": "", "elapsed_ms": 5000}).json()
        check("registration toggle closes signup", not closed.get("success"))
        jpost(owner, "/api/admin/settings", {"values": {"site.registration_enabled": True}}, OH)
        jpost(owner, "/api/admin/settings", {"values": {"site.maintenance": True}}, OH)
        check("maintenance blocks student API", A.get("/api/courses").status_code == 503)
        page = A.get("/")
        check("maintenance blocks student web", page.status_code == 503 and "الصيانة" in page.text)
        check("maintenance keeps staff working", owner.get("/api/admin/settings").status_code == 200)
        blocked_login = client().post("/api/auth/login", json={"phone": AP, "password": STUDENT_PASSWORD}).json()
        check("maintenance blocks student login", not blocked_login.get("success"))
        jpost(owner, "/api/admin/settings", {"values": {"site.maintenance": False}}, OH)
        check("maintenance lifts cleanly", A.get("/api/courses").status_code == 200)
        # ---- owner-only security policy ----
        check("admin cannot read owner security policy", ADM.get("/api/admin/security").status_code == 403)
        sec = owner.get("/api/admin/security").json()["data"]
        check("security policy has bounded specs", sec["specs"]["security.password_min_length"]["min"] == 12)
        check("security policy saves", jpost(owner, "/api/admin/security", {"values": {"security.password_min_length": 14}}, OH).get("success"))
        weak = client().post("/api/auth/register", json={"phone": phone(), "password": "Aa1!aaaaaaaaa", "name": "weak", "guardian_phone": phone(), "division_id": 1, "website": "", "elapsed_ms": 5000}).json()
        check("raised password minimum enforced", not weak.get("success"))
        check("out-of-range security value rejected", owner.post("/api/admin/security", json={"values": {"security.lockout_minutes": 999}}, headers=OH).status_code == 422)
        jpost(owner, "/api/admin/security", {"values": {"security.password_min_length": 12, "security.session_idle_minutes": 5}}, OH)
        asyncio.run(expire_session(AP))
        check("changed idle timeout enforced server-side", A.get("/api/dashboard").status_code == 401)
        jpost(owner, "/api/admin/security", {"values": {"security.session_idle_minutes": 30}}, OH)
        AH, AID = login(A, AP)
        # ---- users / divisions ----
        users = owner.get("/api/admin/users", params={"q": MARK}).json()["data"]
        check("admin user search finds fixtures", users["total"] >= 5)
        check("admin user pagination metadata", users["pages"] >= 1 and users["page"] == 1)
        r = jpost(owner, f"/api/admin/users/{AID}", {"name": MARK + "-renamed", "guardian_phone": "01000000002", "division_id": 2}, OH)
        check("admin edits core user fields", r.get("success"))
        check("admin phone duplicate rejected", owner.post(f"/api/admin/users/{AID}", json={"phone": BP}, headers=OH).status_code == 409)
        check("moderator cannot edit core fields", MOD.post(f"/api/admin/users/{BID}", json={"name": "x"}, headers=MODH).status_code == 403)
        check("owner self-demotion blocked", owner.post(f"/api/admin/users/{OID}", json={"role": "admin"}, headers=OH).status_code == 400)
        check("full ban works", jpost(owner, "/api/users/ban", {"user_id": BID, "days": 1}, OH).get("success"))
        check("unban restores access", jpost(owner, "/api/users/unban", {"user_id": BID}, OH).get("success"))
        BH, BID = login(B, BP)
        r = jpost(owner, "/api/admin/divisions", {"name": MARK + "-division"}, OH)
        check("division creation works", r.get("success")); division_id = r["data"]["id"]
        check("division rename works", jpost(owner, f"/api/admin/divisions/{division_id}", {"name": MARK + "-division2"}, OH).get("success"))
        check("duplicate division rejected", owner.post("/api/admin/divisions", json={"name": MARK + "-division2"}, headers=OH).status_code == 409)
        # promote staff through the real admin API, then re-login
        for uid, p, role, c in ((TID, TP, "teacher", T), (ADMID, ADMP, "admin", ADM), (MODID, MODP, "moderator", MOD)):
            check(f"owner grants {role}", jpost(owner, f"/api/admin/users/{uid}", {"role": role}, OH).get("success"))
        TH, TID = login(T, TP); ADMH, ADMID = login(ADM, ADMP); MODH, MODID = login(MOD, MODP)
        check("moderator can suspend student", jpost(MOD, f"/api/admin/users/{BID}/status", {"status": "suspended"}, MODH).get("success"))
        check("suspended student login rejected", not client().post("/api/auth/login", json={"phone": BP, "password": STUDENT_PASSWORD}).json().get("success"))
        check("moderator can reactivate student", jpost(MOD, f"/api/admin/users/{BID}/status", {"status": "active"}, MODH).get("success"))
        BH, BID = login(B, BP)
        check("admin cannot grant admin role", ADM.post(f"/api/admin/users/{BID}", json={"role": "admin"}, headers=ADMH).status_code == 403)
        check("admin can read settings", ADM.get("/api/admin/settings").status_code == 200)
        check("W5 admin areas are implemented", all(owner.get("/admin/" + x).status_code == 200 for x in ("purchases", "broadcasts", "campaigns", "live")))
        check("student cannot open W5 admin areas", A.get("/admin/purchases").status_code in (303, 307) and "/login" in A.get("/admin/purchases").headers.get("location", ""))
        check("teacher cannot read settings", T.get("/api/admin/settings").status_code == 403)
        jpost(owner, f"/api/admin/users/{AID}", {"division_id": 1}, OH)
        # ---- custom fields ----
        r = jpost(owner, "/api/custom-fields", {"applies_to": "user", "machine_name": "w4_guardian_" + RUN, "label": "ولي إضافي", "field_type": "text", "required": False, "sort_order": 1}, OH)
        check("user text field created", r.get("success")); guardian_field = r["data"]["id"]
        r = jpost(owner, "/api/custom-fields", {"applies_to": "user", "machine_name": "w4_track_" + RUN, "label": "المسار", "field_type": "select", "options": ["علمي", "أدبي"], "required": True, "sort_order": 2}, OH)
        check("user select field created", r.get("success")); track_field = r["data"]["id"]
        r = jpost(owner, "/api/custom-fields", {"applies_to": "course", "machine_name": "w4_hours_" + RUN, "label": "عدد الساعات", "field_type": "number", "required": True}, OH)
        check("course number field created", r.get("success")); hours_field = r["data"]["id"]
        check("invalid machine name rejected", owner.post("/api/custom-fields", json={"applies_to": "user", "machine_name": "Bad Name", "label": "x", "field_type": "text"}, headers=OH).status_code == 422)
        gname, tname, hname = "w4_guardian_" + RUN, "w4_track_" + RUN, "w4_hours_" + RUN
        check("invalid select option rejected", A.post(f"/api/custom-fields/user/{AID}/values", json={"values": {gname: "x", tname: "فضائي"}}, headers=AH).status_code == 422)
        check("required custom field enforced", A.post(f"/api/custom-fields/user/{AID}/values", json={"values": {gname: "x"}}, headers=AH).status_code == 422)
        check("custom values save", jpost(A, f"/api/custom-fields/user/{AID}/values", {"values": {gname: "=1+1", tname: "علمي"}}, AH).get("success"))
        check("profile carries custom fields", jpost(A, "/api/users/profile", {"name": MARK + "-student", "title": "", "badge": "", "custom_fields": {gname: "01000000003", tname: "علمي"}}, AH).get("success"))
        vals = A.get("/api/users/me/custom-fields").json()["data"]
        check("profile custom values persist", vals["values"].get(tname) == "علمي")
        check("student cannot read another user's values", A.get(f"/api/custom-fields/user/{BID}/values").status_code == 403)
        r = jpost(T, "/api/courses", {"title": MARK + "-course", "summary": "تقرير", "division_id": 1, "visibility": "visible", "custom_fields": {hname: "12"}}, TH)
        check("teacher creates course with custom field", r.get("success"), r.get("message", "")); course_id = r["data"]["id"]
        check("course number validation rejects text", jpost(T, "/api/courses", {"title": MARK + "-bad", "custom_fields": {hname: "abc"}}, TH).get("success") is False)
        check("course custom values readable", T.get(f"/api/custom-fields/course/{course_id}/values").json()["data"].get(hname) == "12")
        check("course custom values update", jpost(T, f"/api/custom-fields/course/{course_id}/values", {"values": {hname: "18"}}, TH).get("success"))
        r = jpost(owner, "/api/courses", {"title": MARK + "-other", "division_id": 1, "visibility": "visible", "custom_fields": {hname: "1"}}, OH)
        other_course = r["data"]["id"]
        check("teacher cannot edit another teacher's course fields", T.post(f"/api/custom-fields/course/{other_course}/values", json={"values": {hname: "1"}}, headers=TH).status_code == 403)
        check("field label update works", jpost(owner, f"/api/custom-fields/{guardian_field}", {"label": "ولي أمر إضافي", "options": [], "required": False, "enabled": True, "sort_order": 1}, OH).get("success"))
        # ---- dashboard builder ----
        blocks = A.get("/api/dashboard").json()["data"]
        check("role dashboard defaults seeded", len(blocks) == 8)
        reordered = [{"key": b["key"], "enabled": b["key"] != "chat", "order": i} for i, b in enumerate(reversed(blocks))]
        check("personal dashboard preferences save", jpost(A, "/api/dashboard/preferences", {"blocks": reordered}, AH).get("success"))
        saved = A.get("/api/dashboard").json()["data"]
        check("dashboard order persists", saved[0]["key"] == reordered[0]["key"] and not next(b for b in saved if b["key"] == "chat")["enabled"])
        check("duplicate dashboard order rejected", A.post("/api/dashboard/preferences", json={"blocks": [{**b, "order": 0} for b in reordered]}, headers=AH).status_code == 422)
        defaults = owner.get("/api/admin/dashboard/defaults/student").json()["data"]
        changed = [{**b, "enabled": b["key"] != "digest", "order": b["order"]} for b in defaults]
        check("admin role defaults save", jpost(owner, "/api/admin/dashboard/defaults", {"role": "student", "blocks": changed}, OH).get("success"))
        jpost(owner, "/api/admin/dashboard/defaults", {"role": "student", "blocks": defaults}, OH)
        # ---- theme designer ----
        r = jpost(owner, "/api/admin/themes", {"name": MARK + "-theme", "base_theme": "light", "primary": "#113B77", "secondary": "#2FBCF9", "accent": "#F8B43C", "radius": 12, "density": "compact"}, OH)
        check("brand-palette theme preset created", r.get("success")); preset_id = r["data"]["id"]; preset_key = r["data"]["key"]
        check("arbitrary theme color rejected", owner.post("/api/admin/themes", json={"name": "bad", "primary": "#ff0000", "secondary": "#2FBCF9", "accent": "#F8B43C"}, headers=OH).status_code == 422)
        check("theme activation works", jpost(owner, "/api/admin/themes/activate", {"theme_key": preset_key}, OH).get("success"))
        check("generated theme CSS uses variables", f'--primary:#113B77' in owner.get("/theme.css").text)
        check("active preset cannot be deleted", owner.delete(f"/api/admin/themes/{preset_id}", headers=OH).status_code == 409)
        check("role theme override works", jpost(owner, "/api/admin/themes/role", {"role": "teacher", "theme_key": preset_key}, OH).get("success"))
        check("role override visible to teacher", T.get("/api/themes").json()["data"]["active"] == preset_key)
        jpost(owner, "/api/admin/themes/activate", {"theme_key": "light"}, OH)
        jpost(owner, "/api/admin/themes/role", {"role": "teacher", "theme_key": "light"}, OH)
        check("unused preset can be deleted", owner.delete(f"/api/admin/themes/{preset_id}", headers=OH).status_code == 200)
        preset_id = 0
        # ---- menu builder ----
        r = jpost(owner, "/api/admin/menus", {"label": MARK + "-menu", "url": "/courses", "icon": "book", "role": "student", "order": 5, "enabled": True}, OH)
        check("internal menu item created", r.get("success")); menu_id = r["data"]["id"]
        check("role-targeted menu appears", MARK + "-menu" in A.get("/").text)
        check("menu hidden from other roles", MARK + "-menu" not in T.get("/").text)
        check("javascript menu URL rejected", owner.post("/api/admin/menus", json={"label": "x", "url": "javascript:alert(1)", "icon": "book"}, headers=OH).status_code == 422)
        check("external menu URL rejected", owner.post("/api/admin/menus", json={"label": "x", "url": "https://example.com", "icon": "book"}, headers=OH).status_code == 422)
        check("menu update works", jpost(owner, f"/api/admin/menus/{menu_id}", {"label": MARK + "-menu", "url": "/library", "icon": "library", "role": "student", "order": 6, "enabled": True}, OH).get("success"))
        check("menu delete works", owner.delete(f"/api/admin/menus/{menu_id}", headers=OH).status_code == 200); menu_id = 0
        # ---- reports + exports ----
        check("student enrols for report fixture", jpost(A, f"/api/courses/{course_id}/enrol", {}, AH).get("success"))
        asyncio.run(seed_attempt(course_id, TID))
        # attempts belong to the student for gradebook rows
        async def fix_attempt_user():
            from sqlalchemy import update, select
            from app.core.db import get_sessionmaker, dispose_db
            from app import models as m
            async with get_sessionmaker()() as db:
                eids = (await db.execute(select(m.Exam.id).where(m.Exam.course_id == course_id))).scalars().all()
                await db.execute(update(m.ExamAttempt).where(m.ExamAttempt.exam_id.in_(eids)).values(user_id=AID))
                await db.commit()
            await dispose_db()
        asyncio.run(fix_attempt_user())
        today = date.today().isoformat(); prior = (date.today() - timedelta(days=30)).isoformat()
        params = {"date_from": prior, "date_to": today, "course_id": course_id}
        enrol = T.get("/api/reports/enrolments", params=params).json()["data"]
        check("enrolment report has real rows", enrol["total"] >= 1)
        grades = T.get("/api/reports/grades", params=params).json()["data"]
        check("grade report uses best attempt", any(r[4] == 8 for r in grades["rows"]))
        usage = T.get("/api/reports/usage", params=params).json()["data"]
        check("usage report aggregates activity", usage["total"] >= 1)
        activity = T.get("/api/reports/activity", params=params).json()["data"]
        check("activity report aggregates metrics", activity["total"] >= 1)
        filtered = T.get("/api/reports/enrolments", params={**params, "custom_field": "user:" + gname, "custom_value": "01000000003"}).json()["data"]
        check("custom user field filters reports", any(r[0].endswith("-student") for r in filtered["rows"]))
        check("teacher cannot report outside owned courses", T.get("/api/reports/enrolments", params={"course_id": other_course}).status_code == 403)
        check("student cannot view reports", A.get("/api/reports/enrolments").status_code == 403)
        check("teacher cannot export audit", T.get("/api/reports/audit").status_code == 403)
        check("owner audit report works", owner.get("/api/reports/audit").json()["data"]["total"] >= 1)
        check("invalid report range rejected", owner.get("/api/reports/enrolments", params={"date_from": "2020-01-01", "date_to": "2026-01-01"}).status_code == 422)
        csv_res = T.get("/api/reports/enrolments/export/csv", params=params)
        check("CSV export has UTF-8 BOM", csv_res.status_code == 200 and csv_res.content.startswith(b"\xef\xbb\xbf"))
        xlsx_res = T.get("/api/reports/grades/export/xlsx", params=params)
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(xlsx_res.content)); ws = wb.active
        check("Excel export is a real RTL workbook", xlsx_res.status_code == 200 and ws.sheet_view.rightToLeft and ws.freeze_panes == "A2")
        check("Excel header uses brand blue", ws["A1"].fill.fgColor.rgb and ws["A1"].fill.fgColor.rgb.endswith("0848A4"))
        from app.core.reports import safe_cell
        check("spreadsheet formula injection neutralized", safe_cell('=HYPERLINK("x")').startswith("'=") and safe_cell("+1").startswith("'+"))
        audit_export = owner.get("/api/reports/audit/export/csv")
        check("audit export downloads", audit_export.status_code == 200)
        async def has_export_audit():
            from sqlalchemy import select
            from app.core.db import get_sessionmaker, dispose_db
            from app.models import AuditLog
            async with get_sessionmaker()() as db:
                row = (await db.execute(select(AuditLog).where(AuditLog.action == "report.exported"))).first()
            await dispose_db()
            return row is not None
        check("export action recorded in audit", asyncio.run(has_export_audit()))
        # ---- plugin settings ----
        plugins = owner.get("/api/plugins").json()["data"]
        backup_plugin = next(p for p in plugins if p["component"] == "tool_backup")
        if backup_plugin["status"] == "present":
            check("backup plugin installs", jpost(owner, "/api/plugins/install", {"component": "tool_backup"}, OH).get("success"))
        if backup_plugin["status"] != "enabled":
            check("backup plugin enables", jpost(owner, "/api/plugins/enable", {"component": "tool_backup"}, OH).get("success"))
        ps = owner.get("/api/plugins/tool_backup/settings").json()["data"]
        check("plugin settings are typed", len(ps) == 3 and any(s["name"] == "keep_days" and s["type"] == "int" for s in ps))
        check("plugin settings save", jpost(owner, "/api/plugins/tool_backup/settings", {"values": {"enabled": "1", "keep_days": "7", "include_uploads": "0"}}, OH).get("success"))
        check("plugin setting range enforced", owner.post("/api/plugins/tool_backup/settings", json={"values": {"keep_days": "0"}}, headers=OH).status_code == 422)
        check("student cannot change plugin settings", A.post("/api/plugins/tool_backup/settings", json={"values": {"enabled": "0"}}, headers=AH).status_code == 403)
        # ---- cron / tasks / backups ----
        tasks_data = owner.get("/api/admin/tasks").json()["data"]
        cleanup_task = next(t for t in tasks_data["tasks"] if t["key"] == "core.cleanup")
        digest_task = next(t for t in tasks_data["tasks"] if t["key"] == "core.forum_digest")
        backup_task = next(t for t in tasks_data["tasks"] if t["key"] == "tool_backup.task.run_backup")
        check("core and plugin tasks registered", len(tasks_data["tasks"]) >= 3)
        check("invalid cron schedule rejected", owner.post(f"/api/admin/tasks/{cleanup_task['id']}", json={"minute": "99", "hour": "*", "day": "*", "dayofweek": "*", "month": "*", "enabled": True}, headers=OH).status_code == 422)
        check("cron schedule update works", jpost(owner, f"/api/admin/tasks/{cleanup_task['id']}", {"minute": "*/10", "hour": "*", "day": "*", "dayofweek": "*", "month": "*", "enabled": True}, OH).get("success"))
        from app.core.cron import parse_field, next_run
        from app.models import ScheduledTask
        check("cron parser supports steps/ranges", parse_field("*/15", 0, 59) == {0, 15, 30, 45} and parse_field("1-3", 0, 6) == {1, 2, 3})
        tk = ScheduledTask(classname="x", minute="0", hour="3", day="*", dayofweek="*", month="*")
        check("cron next_run is future", next_run(tk) > utcnow())
        asyncio.run(cron_regressions(AID))
        asyncio.run(wait_unlock(cleanup_task["id"]))
        check("manual cleanup run succeeds", jpost(owner, f"/api/admin/tasks/{cleanup_task['id']}/run", {}, OH).get("success"))
        asyncio.run(lock_task(cleanup_task["id"], True))
        check("locked task cannot run twice", owner.post(f"/api/admin/tasks/{cleanup_task['id']}/run", headers=OH).status_code == 409)
        asyncio.run(lock_task(cleanup_task["id"], False))
        check("cron endpoint rejects missing token", client().post("/api/cron/run").status_code == 403)
        from app import config
        maxid = asyncio.run(set_task_due("core.forum_digest"))
        cron_res = client().post("/api/cron/run", headers={"X-Cron-Token": config.CRON_TOKEN})
        check("token-protected cron executes due tasks", cron_res.status_code == 200 and any(r["task"] == "core.forum_digest" for r in cron_res.json()["data"]["runs"]))
        r = jpost(owner, f"/api/admin/tasks/{backup_task['id']}/run", {}, OH)
        check("scheduled backup task creates real dump", r.get("success") and r.get("data", {}).get("detail", {}).get("backup_id"), r.get("message", ""))
        backup_id = r.get("data", {}).get("detail", {}).get("backup_id", 0)
        backups = owner.get("/api/admin/backups").json()["data"]
        row = next((b for b in backups if b["id"] == backup_id), {})
        check("backup artifact is ready with checksum", row.get("status") == "ready" and len(row.get("sha256", "")) == 64)
        dl = owner.get(f"/api/admin/backups/{backup_id}/download")
        check("owner backup download matches checksum", dl.status_code == 200 and hashlib.sha256(dl.content).hexdigest() == row.get("sha256"))
        try:
            import pgserver
            pgrestore = pathlib.Path(pgserver.__file__).parent / "pginstall" / "bin" / "pg_restore"
            tmp = pathlib.Path("/tmp") / f"tt-w4-{RUN}.dump"; tmp.write_bytes(dl.content)
            listed = subprocess.run([str(pgrestore), "--list", str(tmp)], capture_output=True, text=True, timeout=30)
            check("pg_restore can list the backup", listed.returncode == 0 and "TABLE" in listed.stdout)
            tmp.unlink(missing_ok=True)
        except ImportError:
            check("pg_restore can list the backup", dl.content.startswith(b"PGDMP"))
        check("student cannot download backups", A.get(f"/api/admin/backups/{backup_id}/download").status_code == 403)
        r = jpost(owner, "/api/admin/backups", {"include_uploads": True}, OH)
        check("backup with uploads creates archive", r.get("success")); archive_id = r["data"]["id"]
        archive = owner.get(f"/api/admin/backups/{archive_id}/download")
        with tarfile.open(fileobj=io.BytesIO(archive.content), mode="r:gz") as tar:
            names = tar.getnames()
        check("upload archive contains dump and storage", "database.dump" in names and any(n.startswith("storage") for n in names))
        check("upload archive excludes previous backups", not any(n.startswith("storage/backups") for n in names))
        check("backup delete works", owner.delete(f"/api/admin/backups/{archive_id}", headers=OH).status_code == 200)
        # Prove the separate long-running worker (not only the HTTP endpoint) runs.
        maxid = asyncio.run(set_task_due("core.cleanup"))
        check("background cron worker executes due task", asyncio.run(wait_worker("core.cleanup", maxid)))
        runs = owner.get("/api/admin/tasks").json()["data"]["runs"]
        check("task history records success", any(r["status"] == "success" for r in runs))
        # restore quiet defaults
        jpost(owner, "/api/admin/tasks/" + str(cleanup_task["id"]), {"minute": "15", "hour": "3", "day": "*", "dayofweek": "*", "month": "*", "enabled": True}, OH)
        jpost(owner, "/api/plugins/tool_backup/settings", {"values": {"enabled": "1", "keep_days": "30", "include_uploads": "0"}}, OH)
        jpost(owner, "/api/admin/settings", {"values": {"site.registration_enabled": True, "site.maintenance": False}}, OH)
    finally:
        asyncio.run(cleanup())
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok]); sys.exit(1)
    print("ALL WAVE-4 CHECKS PASSED")


if __name__ == "__main__":
    main()
