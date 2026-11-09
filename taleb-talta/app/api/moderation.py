"""Report queue, sticker approval, dictionary management and scoped restrictions."""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import files, moderation, ratelimit, community
from app.core.audit import audit
from app.core.capabilities import tt_can
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip
from app.api.chat import _quota
from app.models import (User, Attachment, Sticker, ChatMessage, DiscussionPost,
                        QuestionPost, ContentReport, ModerationAction, ModerationStrike,
                        UserRestriction, ProfanityWord, AuditLog, utcnow)

router = APIRouter(prefix="/api", tags=["moderation"])
_ENTITIES = {"forum_post": DiscussionPost, "chat_message": ChatMessage,
             "question_post": QuestionPost, "sticker": Sticker}


async def _sticker_data(db, st):
    a = (await db.execute(select(Attachment).where(Attachment.id == st.attachment_id))).scalar_one()
    owner = (await db.execute(select(User.name).where(User.id == st.owner_id))).scalar_one()
    return {"id": st.id, "title": st.title, "status": st.status, "owner": owner,
            "owner_id": st.owner_id, "reason": st.review_reason,
            "url": "/api/stickers/" + str(st.id) + "/file",
            "created_at": st.created_at.isoformat()}


@router.get("/stickers")
async def stickers(request: Request, mine: bool = False, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    condition = Sticker.owner_id == user.id if mine else Sticker.status == "approved"
    rows = (await db.execute(select(Sticker).where(condition).order_by(Sticker.id.desc()).limit(100))).scalars().all()
    return envelope(True, "", [await _sticker_data(db, s) for s in rows])


@router.post("/stickers")
async def submit_sticker(request: Request, title: str = Form(...), upload: UploadFile = File(...),
                         db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "chat/send")
    await check_csrf(request, sess)
    await moderation.require_communication(db, user)
    result = await moderation.screen(db, user, {"title": title}, source="sticker", ip=client_ip(request))
    if not result.values["title"].strip():
        return envelope(False, "err.required")
    if not await ratelimit.hit(db, f"sticker:{user.id}", 10, 3600):
        await db.commit()
        return envelope(False, "err.rate_limited")
    try:
        data = await files.read_upload(upload)
        if len(data) > 2 * 1024 * 1024:
            raise files.FileError("sticker.too_large")
        await _quota(db, user.id, len(data))
        saved = files.save("stickers", upload.filename or "sticker", data)
        if saved["mime"] not in ("image/png", "image/jpeg", "image/webp"):
            files.delete(saved["key"])
            raise files.FileError("sticker.image_required")
    except files.FileError as e:
        return envelope(False, e.key)
    a = Attachment(owner_id=user.id, purpose="sticker", file_path=saved["key"],
                   file_name=saved["file_name"], file_size=saved["file_size"],
                   mime=saved["mime"], sha256=saved["sha256"])
    db.add(a)
    await db.flush()
    st = Sticker(owner_id=user.id, attachment_id=a.id, title=result.values["title"][:120], status="pending")
    db.add(st)
    await db.flush()
    await audit(db, action="sticker.submitted", actor=user, entity_type="sticker",
                entity_id=st.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, result.message_key or "sticker.submitted", {"id": st.id})


@router.get("/stickers/{sticker_id}/file")
async def sticker_file(sticker_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    st = (await db.execute(select(Sticker).where(Sticker.id == sticker_id))).scalar_one_or_none()
    if st is None:
        raise HTTPException(404, "err.not_found")
    if st.status != "approved" and st.owner_id != user.id and not await tt_can(db, user, "sticker/approve"):
        raise HTTPException(403, "sticker.not_approved")
    a = (await db.execute(select(Attachment).where(Attachment.id == st.attachment_id))).scalar_one()
    return files.gateway(files.resolve(a.file_path), a.file_name, a.mime, inline=True)


@router.get("/stickers/pending")
async def pending_stickers(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "sticker/approve")
    rows = (await db.execute(select(Sticker).where(Sticker.status == "pending").order_by(Sticker.id))).scalars().all()
    return envelope(True, "", [await _sticker_data(db, s) for s in rows])


class ReviewIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


@router.post("/stickers/{sticker_id}/approve")
@router.post("/stickers/{sticker_id}/reject")
async def review_sticker(sticker_id: int, body: ReviewIn, request: Request,
                         db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "sticker/approve")
    await check_csrf(request, sess)
    st = (await db.execute(select(Sticker).where(Sticker.id == sticker_id))).scalar_one_or_none()
    if st is None:
        raise HTTPException(404, "err.not_found")
    if st.status != "pending":
        return envelope(False, "moderation.already_reviewed")
    approve = request.url.path.endswith("/approve")
    if not approve and not body.reason.strip():
        return envelope(False, "err.reject_reason_required")
    st.status = "approved" if approve else "rejected"
    st.review_reason = "" if approve else body.reason.strip()
    st.reviewed_by, st.reviewed_at = user.id, utcnow()
    db.add(ModerationAction(actor_id=user.id, target_user_id=st.owner_id,
                            decision="approve" if approve else "remove", reason=st.review_reason))
    await audit(db, action="sticker." + st.status, actor=user, entity_type="sticker",
                entity_id=st.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "sticker.approved" if approve else "sticker.rejected")


async def _entity(db, user, entity_type, entity_id, *, staff=False):
    model = _ENTITIES.get(entity_type)
    if model is None:
        raise HTTPException(404, "err.not_found")
    obj = (await db.execute(select(model).where(model.id == entity_id))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "err.not_found")
    if entity_type == "chat_message":
        if not staff:
            await community.membership(db, obj.channel_id, user)
        return obj, obj.sender_id, obj.body, "/chat?channel=" + str(obj.channel_id)
    if entity_type == "forum_post":
        from app.api.forum import get_thread
        thread = await get_thread(db, user, obj.thread_id)
        return obj, obj.user_id, obj.body, "/forum/" + str(thread.id) + "#post-" + str(obj.id)
    if entity_type == "question_post":
        from app.api.exams import _get_question
        await _get_question(db, obj.question_id)
        if not staff and obj.user_id != user.id and not await tt_can(db, user, "exam/grade"):
            # Existing question comments are visible to authenticated learners.
            pass
        return obj, obj.user_id, obj.body, "/exams"
    if entity_type == "sticker":
        if obj.status != "approved" and obj.owner_id != user.id and not staff:
            raise HTTPException(403, "sticker.not_approved")
        return obj, obj.owner_id, obj.title, "/chat"


class ReportIn(BaseModel):
    entity_type: str
    entity_id: int
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/moderation/reports")
async def report(body: ReportIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    obj, target_id, snapshot, _ = await _entity(db, user, body.entity_type, body.entity_id)
    await db.commit()
    if target_id == user.id:
        return envelope(False, "moderation.cannot_report_self")
    existing = (await db.execute(select(ContentReport).where(
        ContentReport.reporter_id == user.id, ContentReport.target_type == body.entity_type,
        ContentReport.entity_id == body.entity_id))).scalar_one_or_none()
    if existing:
        return envelope(False, "moderation.already_reported")
    if not await ratelimit.hit(db, f"report:{user.id}", 20, 3600):
        await db.commit()
        return envelope(False, "err.rate_limited")
    result = await moderation.screen(db, user, {"reason": body.reason}, source="report",
                                     count_strike=False)
    row = ContentReport(reporter_id=user.id, target_type=body.entity_type, entity_id=body.entity_id,
                        reason=result.values["reason"], snapshot=snapshot[:4000], status="pending")
    db.add(row)
    await db.flush()
    await audit(db, action="moderation.reported", actor=user, entity_type=body.entity_type,
                entity_id=body.entity_id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "moderation.reported", {"id": row.id})


async def _report_data(db, r, reporter, target_name):
    _, _, _, link = await _entity(db, None, r.target_type, r.entity_id, staff=True)
    return {"id": r.id, "entity_type": r.target_type, "entity_id": r.entity_id,
            "reason": r.reason, "snapshot": r.snapshot, "status": r.status,
            "reporter": reporter, "target_name": target_name, "link": link,
            "created_at": r.created_at.isoformat()}


@router.get("/moderation/reports")
async def reports(request: Request, status: str = "pending", db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "moderation/review")
    if status not in ("pending", "resolved", "dismissed", "all"):
        return envelope(False, "err.field_invalid")
    stmt = select(ContentReport, User.name).join(User, User.id == ContentReport.reporter_id)
    if status != "all":
        stmt = stmt.where(ContentReport.status == status)
    rows = (await db.execute(stmt.order_by(ContentReport.id).limit(200))).all()
    out = []
    for r, name in rows:
        _, target_id, _, _ = await _entity(db, None, r.target_type, r.entity_id, staff=True)
        target_name = (await db.execute(select(User.name).where(User.id == target_id))).scalar_one()
        out.append(await _report_data(db, r, name, target_name))
    return envelope(True, "", out)


class DecisionIn(BaseModel):
    action: str
    reason: str = Field(default="", max_length=2000)


@router.post("/moderation/reports/{report_id}/decide")
async def decide(report_id: int, body: DecisionIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "moderation/review")
    await check_csrf(request, sess)
    if body.action not in ("approve", "remove", "warn", "ban"):
        return envelope(False, "err.field_invalid")
    if body.action != "approve" and not body.reason.strip():
        return envelope(False, "moderation.reason_required")
    r = (await db.execute(select(ContentReport).where(ContentReport.id == report_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(404, "err.not_found")
    if r.status != "pending":
        return envelope(False, "moderation.already_reviewed")
    obj, target_id, _, _ = await _entity(db, user, r.target_type, r.entity_id, staff=True)
    target = (await db.execute(select(User).where(User.id == target_id))).scalar_one()
    ip = client_ip(request)
    if body.action == "ban" and not await tt_can(db, user, "user/ban"):
        raise HTTPException(403, "err.forbidden")
    # Flush the report state before scoped-ban helper commits its transaction.
    r.status = "dismissed" if body.action == "approve" else "resolved"
    r.reviewed_by, r.reviewed_at = user.id, utcnow()
    if body.action == "remove":
        if r.target_type == "sticker":
            obj.status = "rejected"
            obj.review_reason = body.reason
            obj.reviewed_by, obj.reviewed_at = user.id, utcnow()
        else:
            obj.deleted_at = utcnow()
        db.add(ModerationAction(actor_id=user.id, target_user_id=target.id, report_id=r.id,
                                decision="remove", reason=body.reason))
    elif body.action == "approve":
        db.add(ModerationAction(actor_id=user.id, target_user_id=target.id, report_id=r.id,
                                decision="approve", reason=body.reason))
    await audit(db, action="moderation.decision", actor=user, entity_type="content_report",
                entity_id=r.id, after={"decision": body.action, "reason": body.reason}, ip=ip, severity="notice")
    await db.commit()
    if body.action == "warn":
        await moderation.record_violation(db, target, source="moderation.report", ip=ip,
                                          actor=user, reason=body.reason, report_id=r.id)
    elif body.action == "ban":
        await moderation.ban_user(db, target, actor=user, reason=body.reason, report_id=r.id, ip=ip)
    related = (await db.execute(select(ContentReport).where(
        ContentReport.target_type == r.target_type, ContentReport.entity_id == r.entity_id,
        ContentReport.status == "pending"))).scalars().all()
    for other in related:
        other.status = r.status
        other.reviewed_by, other.reviewed_at = user.id, utcnow()
    await db.commit()
    return envelope(True, "moderation.decision_saved")


@router.get("/moderation/overview")
async def overview(request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "moderation/review")
    pending = (await db.execute(select(func.count(ContentReport.id)).where(ContentReport.status == "pending"))).scalar_one()
    stickers_pending = (await db.execute(select(func.count(Sticker.id)).where(Sticker.status == "pending"))).scalar_one()
    alerts = (await db.execute(select(AuditLog).where(
        AuditLog.action == "user.banned_login_attempt").order_by(AuditLog.id.desc()).limit(10))).scalars().all()
    restrictions = (await db.execute(select(UserRestriction, User.name).join(User, User.id == UserRestriction.user_id)
                    .where(UserRestriction.revoked_at.is_(None), UserRestriction.expires_at > utcnow())
                    .order_by(UserRestriction.id.desc()).limit(100))).all()
    alert_rows = []
    for a in alerts:
        name = (await db.execute(select(User.name).where(User.id == a.actor_id))).scalar_one_or_none() if a.actor_id else None
        alert_rows.append({"id": a.id, "user_id": a.actor_id, "name": name, "created_at": a.created_at.isoformat()})
    return envelope(True, "", {"reports": pending, "stickers": stickers_pending,
        "alerts": alert_rows,
        "restrictions": [{"id": r.id, "user_id": r.user_id, "name": name, "scope": r.scope,
                          "expires_at": r.expires_at.isoformat(), "reason": r.reason} for r, name in restrictions],
        "can_ban": await tt_can(db, actor, "user/ban")})


@router.get("/moderation/profanity")
async def list_words(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "moderation/review")
    rows = (await db.execute(select(ProfanityWord).order_by(ProfanityWord.id))).scalars().all()
    return envelope(True, "", [{"id": w.id, "word": w.word, "enabled": w.enabled} for w in rows])


class WordIn(BaseModel):
    word: str = Field(min_length=1, max_length=120)
    enabled: bool = True


@router.post("/moderation/profanity")
async def add_word(body: WordIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "moderation/review")
    await check_csrf(request, sess)
    word = moderation.normalize(body.word)
    if not word or len(word.split()) > 3:
        return envelope(False, "err.field_invalid")
    row = (await db.execute(select(ProfanityWord).where(ProfanityWord.word == word))).scalar_one_or_none()
    if row:
        row.enabled = body.enabled
    else:
        row = ProfanityWord(word=word, enabled=body.enabled, created_by=user.id)
        db.add(row)
    await audit(db, action="moderation.dictionary_updated", actor=user, entity_type="profanity",
                entity_id=word, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "moderation.dictionary_saved")


class WordStateIn(BaseModel):
    enabled: bool


@router.post("/moderation/profanity/{word_id}/state")
async def word_state(word_id: int, body: WordStateIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "moderation/review")
    await check_csrf(request, sess)
    row = (await db.execute(select(ProfanityWord).where(ProfanityWord.id == word_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    row.enabled = body.enabled
    await audit(db, action="moderation.dictionary_updated", actor=user, entity_type="profanity",
                entity_id=row.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated")


class LiftIn(BaseModel):
    restriction_id: int
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/moderation/restrictions/lift")
async def lift(body: LiftIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "user/ban")
    await check_csrf(request, sess)
    row = (await db.execute(select(UserRestriction).where(UserRestriction.id == body.restriction_id))).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return envelope(False, "err.not_found")
    row.revoked_at = utcnow()
    await audit(db, action="moderation.restriction_lifted", actor=user, entity_type="user",
                entity_id=row.user_id, after={"reason": body.reason}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "moderation.restriction_lifted")
