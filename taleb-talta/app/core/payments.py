"""Manual settlement only: a request is never proof of payment.

Confirmed purchases are the entitlement source. Enrolment rows alone never
unlock paid content, and a per-lesson purchase never unlocks its siblings.
"""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.core.capabilities import tt_can
from app.core.audit import audit
from app.models import (Purchase, Course, CourseSection, Lesson, CourseStudent,
                        User, utcnow)

MAX_PRICE = 100_000_000  # EGP cents; bounded integer arithmetic, no floats


async def manage_course(db, user, course: Course) -> bool:
    return await tt_can(db, user, "course/edit") and (
        user.role in ("owner", "admin") or course.teacher_id == user.id)


async def enrolled(db, user_id: int, course_id: int) -> bool:
    return (await db.execute(select(CourseStudent.id).where(
        CourseStudent.user_id == user_id, CourseStudent.course_id == course_id))).first() is not None


async def confirmed(db, user_id: int, course_id: int, lesson_id: int | None = None) -> bool:
    condition = Purchase.lesson_id.is_(None) if lesson_id is None else Purchase.lesson_id == lesson_id
    return (await db.execute(select(Purchase.id).where(
        Purchase.user_id == user_id, Purchase.course_id == course_id,
        Purchase.status == "confirmed", condition))).first() is not None


async def course_access(db, user, course: Course) -> bool:
    """Access to the course catalogue/header, not necessarily every lesson."""
    if await manage_course(db, user, course):
        return True
    if course.visibility != "visible" or (course.division_id and user.division_id != course.division_id):
        return False
    if course.price_cents > 0:
        return await confirmed(db, user.id, course.id)
    return await enrolled(db, user.id, course.id)


async def learn_access(db, user, course: Course) -> bool:
    if await manage_course(db, user, course):
        return True
    if course.visibility != "visible" or (course.division_id and user.division_id != course.division_id):
        return False
    if course.available_from and utcnow() < course.available_from:
        return False
    if course.available_to and utcnow() > course.available_to:
        return False
    if course.price_cents > 0:
        return await confirmed(db, user.id, course.id)
    return await enrolled(db, user.id, course.id)


async def lesson_access(db, user, course: Course, lesson: Lesson) -> bool:
    if await manage_course(db, user, course):
        return True
    if not await learn_access(db, user, course):
        return False
    if course.price_cents == 0 and lesson.price_cents > 0:
        return await confirmed(db, user.id, course.id, lesson.id)
    return True


async def lesson_context(db, lesson_id: int, *, lock=False):
    q = (select(Lesson, CourseSection, Course)
         .join(CourseSection, CourseSection.id == Lesson.section_id)
         .join(Course, Course.id == CourseSection.course_id)
         .where(Lesson.id == lesson_id, Lesson.deleted_at.is_(None),
                Course.deleted_at.is_(None)))
    if lock:
        q = q.with_for_update()
    row = (await db.execute(q)).first()
    if row is None:
        raise HTTPException(404, "err.lesson_not_found")
    return row  # lesson, section, course


async def require_lesson(db, user, lesson_id: int):
    lesson, section, course = await lesson_context(db, lesson_id)
    if not await lesson_access(db, user, course, lesson):
        # Distinct, stable code required by the product contract.
        paid = course.price_cents > 0 or lesson.price_cents > 0
        raise HTTPException(403, "PAID_CONTENT_LOCKED" if paid else "err.not_enrolled")
    return lesson, section, course


def validate_price(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_PRICE:
        raise HTTPException(422, "purchase.price_invalid")
    return value


async def set_course_price(db, user, course: Course, price: int, *, ip=""):
    validate_price(price)
    if price > 0 and (await db.execute(select(Lesson.id).join(
            CourseSection, CourseSection.id == Lesson.section_id).where(
            CourseSection.course_id == course.id, Lesson.price_cents > 0,
            Lesson.deleted_at.is_(None)))).first():
        raise HTTPException(422, "purchase.mixed_pricing")
    before = course.price_cents
    course.price_cents, course.updated_at = price, utcnow()
    await audit(db, action="course.priced", actor=user, entity_type="course", entity_id=course.id,
                before={"price_cents": before}, after={"price_cents": price}, ip=ip, severity="notice")


async def set_lesson_price(db, user, lesson: Lesson, course: Course, price: int, *, ip=""):
    validate_price(price)
    if price > 0 and course.price_cents > 0:
        raise HTTPException(422, "purchase.mixed_pricing")
    before = lesson.price_cents
    lesson.price_cents = price
    await audit(db, action="lesson.priced", actor=user, entity_type="lesson", entity_id=lesson.id,
                before={"price_cents": before}, after={"price_cents": price}, ip=ip, severity="notice")


async def ensure_enrolment(db, user_id: int, course_id: int):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    await db.execute(pg_insert(CourseStudent).values(user_id=user_id, course_id=course_id,
        method="purchase", enrolled_at=utcnow()).on_conflict_do_nothing(index_elements=["course_id", "user_id"]))


def public(row: Purchase, *, course_title="", lesson_title="", user_name="", phone=""):
    return {"id": row.id, "course_id": row.course_id, "lesson_id": row.lesson_id,
            "course_title": course_title, "lesson_title": lesson_title,
            "user_name": user_name, "phone": phone, "amount_cents": row.amount_cents,
            "currency": row.currency, "status": row.status, "reference": row.reference,
            "note": row.note, "review_note": row.review_note,
            "created_at": row.created_at.isoformat(),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else ""}
