"""Manual purchase requests and staff confirmation. No payment gateway."""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import payments, moderation, ratelimit, settings as site_settings, notifications
from app.core.audit import audit
from app.core.events import bus
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip
from app.models import Purchase, Course, Lesson, CourseSection, User, utcnow

router = APIRouter(tags=["purchases"])


class RequestIn(BaseModel):
    course_id: int
    lesson_id: int = 0
    reference: str = Field(min_length=3, max_length=120)
    note: str = Field(default="", max_length=1000)

class ReviewIn(BaseModel):
    note: str = Field(default="", max_length=1000)

class PriceIn(BaseModel):
    price_cents: int


@router.get("/api/purchases/meta")
async def meta(request: Request, db: AsyncSession = Depends(get_db)):
    await require_user(request, db)
    return envelope(True, "", {"currency": "EGP",
        "support_phone": await site_settings.raw(db, "site.contact_phone"),
        "support_message": await site_settings.raw(db, "site.contact_message")})


async def _rows(db, condition, *, offset=0, limit=200):
    rows = (await db.execute(select(Purchase, Course.title, Lesson.title, User.name, User.phone)
             .join(Course, Course.id == Purchase.course_id)
             .outerjoin(Lesson, Lesson.id == Purchase.lesson_id)
             .join(User, User.id == Purchase.user_id)
             .where(condition).order_by(Purchase.created_at.desc(), Purchase.id.desc()).offset(offset).limit(limit))).all()
    return [payments.public(p, course_title=ct, lesson_title=lt or "", user_name=name, phone=phone)
            for p, ct, lt, name, phone in rows]


@router.get("/api/purchases")
async def mine(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    return envelope(True, "", await _rows(db, Purchase.user_id == user.id))


@router.post("/api/purchases")
async def create(body: RequestIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "purchase/request")
    await check_csrf(request, sess)
    if not await ratelimit.hit(db, f"purchase:{user.id}", 10, 3600):
        await db.commit(); raise HTTPException(429, "err.rate_limited")
    course = (await db.execute(select(Course).where(Course.id == body.course_id,
                Course.deleted_at.is_(None), Course.visibility == "visible").with_for_update())).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "err.course_not_found")
    if course.division_id and user.division_id != course.division_id and user.role not in ("owner", "admin"):
        raise HTTPException(403, "err.forbidden")
    lesson = None
    if body.lesson_id:
        lesson, section, owner_course = await payments.lesson_context(db, body.lesson_id, lock=True)
        if owner_course.id != course.id or course.price_cents > 0 or lesson.price_cents <= 0:
            raise HTTPException(422, "purchase.target_invalid")
        if await payments.confirmed(db, user.id, course.id, lesson.id):
            raise HTTPException(409, "purchase.already_owned")
        amount = lesson.price_cents
    else:
        if course.price_cents <= 0:
            raise HTTPException(422, "purchase.target_invalid")
        if await payments.confirmed(db, user.id, course.id):
            raise HTTPException(409, "purchase.already_owned")
        amount = course.price_cents
    pending = (await db.execute(select(Purchase.id).where(Purchase.user_id == user.id,
        Purchase.course_id == course.id, Purchase.status == "pending",
        Purchase.lesson_id.is_(None) if lesson is None else Purchase.lesson_id == lesson.id))).first()
    if pending:
        raise HTTPException(409, "purchase.already_pending")
    screened = await moderation.screen(db, user, {"reference": body.reference, "note": body.note},
                                       source="purchase.request", count_strike=False)
    if not screened.values["reference"].strip():
        raise HTTPException(422, "err.required")
    row = Purchase(user_id=user.id, course_id=course.id, lesson_id=lesson.id if lesson else None,
                   amount_cents=amount, reference=screened.values["reference"].strip(),
                   note=screened.values["note"])
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback(); raise HTTPException(409, "purchase.already_pending")
    await audit(db, action="purchase.requested", actor=user, entity_type="purchase", entity_id=row.id,
                after={"course_id": course.id, "lesson_id": row.lesson_id, "amount_cents": amount},
                ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "purchase.requested", {"id": row.id, "status": row.status, "amount_cents": amount})


@router.post("/api/purchases/{purchase_id}/cancel")
async def cancel(purchase_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    row = (await db.execute(select(Purchase).where(Purchase.id == purchase_id,
                Purchase.user_id == user.id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    if row.status != "pending":
        raise HTTPException(409, "purchase.not_pending")
    row.status, row.updated_at = "cancelled", utcnow()
    await audit(db, action="purchase.cancelled", actor=user, entity_type="purchase", entity_id=row.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "purchase.cancelled")


@router.get("/api/admin/purchases")
async def admin_list(request: Request, status: str = "", offset: int = 0, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "purchase/confirm")
    if status and status not in ("pending", "confirmed", "rejected", "cancelled"):
        raise HTTPException(422, "err.field_invalid")
    offset = max(0, offset)
    condition = Purchase.status == status if status else True
    rows = await _rows(db, condition, offset=offset, limit=101)
    counts = dict((await db.execute(select(Purchase.status, func.count(Purchase.id)).group_by(Purchase.status))).all())
    return envelope(True, "", {"rows": rows[:100], "counts": counts, "offset": offset,
                               "has_more": len(rows) > 100, "next_offset": offset + 100})


async def _review(db, user, purchase_id: int, decision: str, note: str, ip: str):
    row = (await db.execute(select(Purchase).where(Purchase.id == purchase_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    if row.status != "pending":
        raise HTTPException(409, "purchase.not_pending")
    if decision == "rejected" and not note.strip():
        raise HTTPException(422, "purchase.reject_reason")
    before = row.status
    row.status, row.reviewed_by, row.review_note, row.reviewed_at, row.updated_at = decision, user.id, note.strip()[:1000], utcnow(), utcnow()
    if decision == "confirmed":
        await payments.ensure_enrolment(db, row.user_id, row.course_id)
        await notifications.notify_user(db, row.user_id, "purchase.notification_title",
            "purchase.confirmed_body", kind="purchase", url="/purchases",
            body_params={"id": row.id})
    else:
        await notifications.notify_user(db, row.user_id, "purchase.notification_title",
            "purchase.rejected_body", kind="purchase", url="/purchases", body_params={"id": row.id})
    await audit(db, action="purchase." + decision, actor=user, entity_type="purchase", entity_id=row.id,
                before={"status": before}, after={"status": decision, "amount_cents": row.amount_cents},
                ip=ip, severity="notice")
    return row


@router.post("/api/admin/purchases/{purchase_id}/confirm")
async def confirm(purchase_id: int, body: ReviewIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "purchase/confirm")
    await check_csrf(request, sess)
    row = await _review(db, user, purchase_id, "confirmed", body.note, client_ip(request))
    await db.commit()
    await bus.dispatch("purchase.confirmed", {"purchase_id": row.id, "user_id": row.user_id,
                       "course_id": row.course_id, "lesson_id": row.lesson_id})
    return envelope(True, "ok.purchase_confirmed", {"id": row.id, "status": row.status})


@router.post("/api/admin/purchases/{purchase_id}/reject")
async def reject(purchase_id: int, body: ReviewIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "purchase/confirm")
    await check_csrf(request, sess)
    row = await _review(db, user, purchase_id, "rejected", body.note, client_ip(request))
    await db.commit()
    return envelope(True, "purchase.rejected", {"id": row.id, "status": row.status})


@router.post("/api/courses/{course_id}/pricing")
async def course_price(course_id: int, body: PriceIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/pricing")
    await check_csrf(request, sess)
    course = (await db.execute(select(Course).where(Course.id == course_id,
                Course.deleted_at.is_(None)).with_for_update())).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "err.course_not_found")
    await payments.set_course_price(db, user, course, body.price_cents, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"price_cents": course.price_cents})


@router.post("/api/lessons/{lesson_id}/pricing")
async def lesson_price(lesson_id: int, body: PriceIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/pricing")
    await check_csrf(request, sess)
    lesson, section, course = await payments.lesson_context(db, lesson_id, lock=True)
    await payments.set_lesson_price(db, user, lesson, course, body.price_cents, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"price_cents": lesson.price_cents})
