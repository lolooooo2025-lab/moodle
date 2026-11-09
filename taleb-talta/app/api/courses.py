"""Courses / sections / lessons / lesson-player API (Wave 1).

Capability-gated writes, division-based visibility, availability windows,
enrolment, per-item completion + progress. Question answers are graded on the
server and never sent to the browser before submission.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import files, payments
from app.core.audit import audit
from app.core import moderation, customfields
from app.core.i18n import t
from app.api.deps import (envelope, require_user, require_cap, client_ip,
                          user_agent, check_csrf)
from app.models import (Course, CourseCategory, CourseSection, Lesson, LessonItem,
                        LessonProgress, CourseStudent, Division, User, Purchase, utcnow)

router = APIRouter(prefix="/api", tags=["courses"])

STAFF_ROLES = ("owner", "admin", "teacher")


# ---- helpers --------------------------------------------------------------
async def _is_staff(db, user, cap="course/edit"):
    from app.core.capabilities import tt_can
    return await tt_can(db, user, cap)

async def _get_course(db, course_id) -> Course:
    c = (await db.execute(select(Course).where(
        Course.id == course_id, Course.deleted_at.is_(None)))).scalar_one_or_none()
    if c is None:
        raise HTTPException(status_code=404, detail="err.course_not_found")
    return c

def _available(c: Course) -> str | None:
    now = utcnow()
    if c.available_from and now < c.available_from:
        return "course.not_available_yet"
    if c.available_to and now > c.available_to:
        return "course.not_available_anymore"
    return None

async def _enrolled(db, user, course_id) -> bool:
    row = (await db.execute(select(CourseStudent).where(
        CourseStudent.course_id == course_id,
        CourseStudent.user_id == user.id))).scalar_one_or_none()
    return row is not None

async def _can_learn(db, user, c: Course) -> bool:
    return await payments.learn_access(db, user, c)

async def _lesson_progress(db, user_id, lesson_id) -> int:
    total = (await db.execute(select(func.count(LessonItem.id)).where(
        LessonItem.lesson_id == lesson_id))).scalar_one()
    if total == 0:
        done = (await db.execute(select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id,
            LessonProgress.item_id.is_(None)))).scalar_one()
        return 100 if done else 0
    done = (await db.execute(select(func.count(LessonProgress.id)).where(
        LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id,
        LessonProgress.item_id.is_not(None)))).scalar_one()
    return int(round(100 * min(done, total) / total))


# ---- categories -----------------------------------------------------------
@router.get("/categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(CourseCategory).order_by(
        CourseCategory.sort_order, CourseCategory.name))).scalars().all()
    return envelope(True, "", [{"id": r.id, "name": r.name} for r in rows])

class CategoryIn(BaseModel):
    name: str

@router.post("/categories")
async def create_category(body: CategoryIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/create")
    await check_csrf(request, sess)
    if not body.name.strip():
        return envelope(False, "err.required")
    name = moderation.filter_text(body.name, await moderation.dictionary(db))[0]
    cat = CourseCategory(name=name.strip()[:120])
    db.add(cat)
    await db.flush()
    await audit(db, action="course.category_created", actor=user, entity_type="course_category",
                entity_id=cat.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.created", {"id": cat.id, "name": cat.name})


# ---- courses --------------------------------------------------------------
@router.get("/courses")
async def list_courses(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    staff = await _is_staff(db, user)
    q = select(Course).where(Course.deleted_at.is_(None))
    if not staff:
        q = q.where(Course.visibility == "visible")
    courses = (await db.execute(q.order_by(Course.created_at.desc()))).scalars().all()
    cats = {c.id: c.name for c in (await db.execute(select(CourseCategory))).scalars().all()}
    divs = {d.id: d.name for d in (await db.execute(select(Division))).scalars().all()}
    out = []
    for c in courses:
        avail = _available(c)
        if not staff:
            if c.division_id and user.division_id != c.division_id:
                continue
            if avail:
                continue
        enrolled = await _enrolled(db, user, c.id)
        nlessons = (await db.execute(select(func.count(Lesson.id)).join(
            CourseSection, Lesson.section_id == CourseSection.id).where(
            CourseSection.course_id == c.id, Lesson.deleted_at.is_(None)))).scalar_one()
        out.append({"id": c.id, "title": c.title, "summary": c.summary,
                    "category_name": cats.get(c.category_id, ""),
                    "division_id": c.division_id, "division_name": divs.get(c.division_id, ""),
                    "visibility": c.visibility, "price_cents": c.price_cents,
                    "lesson_count": nlessons, "enrolled": enrolled, "can_learn": await payments.learn_access(db, user, c),
                    "available": avail is None, "available_key": avail or ""})
    return envelope(True, "", out)

class CourseIn(BaseModel):
    title: str
    summary: str = ""
    category_id: int | None = None
    division_id: int | None = None
    visibility: str = "visible"
    custom_fields: dict | None = None

@router.post("/courses")
async def create_course(body: CourseIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/create")
    await check_csrf(request, sess)
    if not body.title.strip():
        return envelope(False, "err.required")
    if body.visibility not in ("visible", "hidden"):
        return envelope(False, "err.field_invalid")
    screened = await moderation.screen(db, user, {"title": body.title, "summary": body.summary}, source="course.create", count_strike=False)
    c = Course(title=screened.values["title"].strip()[:200], summary=screened.values["summary"],
               category_id=body.category_id, division_id=body.division_id,
               visibility=body.visibility, teacher_id=user.id)
    custom = await customfields.validate_values(db, "course", body.custom_fields or {})
    db.add(c)
    await db.flush()
    await customfields.save_values(db, "course", c.id, custom)
    await audit(db, action="course.created", actor=user, entity_type="course",
                entity_id=c.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "course.created", {"id": c.id})

@router.post("/courses/{course_id}/update")
async def update_course(course_id: int, body: CourseIn, request: Request,
                        db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/edit")
    await check_csrf(request, sess)
    c = await _get_course(db, course_id)
    if user.role not in ("owner", "admin") and c.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="err.forbidden")
    screened = await moderation.screen(db, user, {"title": body.title, "summary": body.summary}, source="course.edit", count_strike=False)
    c.title = screened.values["title"].strip()[:200] or c.title
    c.summary = screened.values["summary"]
    c.category_id = body.category_id
    c.division_id = body.division_id
    if body.visibility in ("visible", "hidden"):
        c.visibility = body.visibility
    c.updated_at = utcnow()
    if body.custom_fields is not None:
        custom = await customfields.validate_values(db, "course", body.custom_fields)
        await customfields.save_values(db, "course", c.id, custom)
    await audit(db, action="course.updated", actor=user, entity_type="course",
                entity_id=c.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "course.updated", {"id": c.id})

@router.post("/courses/{course_id}/delete")
async def delete_course(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "course/delete")
    await check_csrf(request, sess)
    c = await _get_course(db, course_id)
    c.deleted_at = utcnow()                      # soft delete (owner purge later)
    await audit(db, action="course.deleted", actor=user, entity_type="course",
                entity_id=c.id, ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "course.deleted")

@router.post("/courses/{course_id}/enrol")
async def enrol(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    c = await _get_course(db, course_id)
    if c.visibility != "visible":
        return envelope(False, "err.forbidden")
    avail = _available(c)
    if avail:
        return envelope(False, avail)
    if c.division_id and user.division_id != c.division_id:
        return envelope(False, "err.forbidden")
    if c.price_cents > 0 and not await payments.confirmed(db, user.id, c.id):
        raise HTTPException(403, "PAID_CONTENT_LOCKED")
    if await _enrolled(db, user, c.id):
        return envelope(False, "err.already_enrolled")
    db.add(CourseStudent(course_id=c.id, user_id=user.id, method="self"))
    await audit(db, action="course.enrolled", actor=user, entity_type="course",
                entity_id=c.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "course.enrolled_ok")


# ---- sections + lessons ---------------------------------------------------
class SectionIn(BaseModel):
    title: str
    summary: str = ""

@router.post("/courses/{course_id}/sections")
async def add_section(course_id: int, body: SectionIn, request: Request,
                      db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "lesson/edit")
    await check_csrf(request, sess)
    c = await _get_course(db, course_id)
    if not body.title.strip():
        return envelope(False, "err.required")
    n = (await db.execute(select(func.count(CourseSection.id)).where(
        CourseSection.course_id == c.id))).scalar_one()
    screened = await moderation.screen(db, user, {"title": body.title, "summary": body.summary}, source="course.section", count_strike=False)
    s = CourseSection(course_id=c.id, title=screened.values["title"].strip()[:200],
                      summary=screened.values["summary"], sort_order=n)
    db.add(s)
    await db.flush()
    await db.commit()
    return envelope(True, "lesson.section_added", {"id": s.id})

class LessonIn(BaseModel):
    title: str
    summary: str = ""

@router.post("/sections/{section_id}/lessons")
async def add_lesson(section_id: int, body: LessonIn, request: Request,
                     db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "lesson/edit")
    await check_csrf(request, sess)
    sec = (await db.execute(select(CourseSection).where(
        CourseSection.id == section_id))).scalar_one_or_none()
    if sec is None:
        return envelope(False, "err.not_found")
    if not body.title.strip():
        return envelope(False, "err.required")
    n = (await db.execute(select(func.count(Lesson.id)).where(
        Lesson.section_id == sec.id, Lesson.deleted_at.is_(None)))).scalar_one()
    screened = await moderation.screen(db, user, {"title": body.title, "summary": body.summary}, source="lesson.create", count_strike=False)
    les = Lesson(section_id=sec.id, title=screened.values["title"].strip()[:200],
                 summary=screened.values["summary"], sort_order=n)
    db.add(les)
    await db.flush()
    await db.commit()
    return envelope(True, "lesson.lesson_added", {"id": les.id})

@router.get("/courses/{course_id}/detail")
async def course_detail(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    c = await _get_course(db, course_id)
    can_learn = await _can_learn(db, user, c)
    staff = await _is_staff(db, user)
    if not can_learn and not staff:
        # still show the course header so the student can enrol
        if c.visibility != "visible" or (c.division_id and user.division_id != c.division_id):
            raise HTTPException(status_code=403, detail="err.forbidden")
    secs = (await db.execute(select(CourseSection).where(
        CourseSection.course_id == c.id).order_by(CourseSection.sort_order))).scalars().all()
    purchased_lessons = set((await db.execute(select(Purchase.lesson_id).where(
        Purchase.user_id == user.id, Purchase.course_id == c.id,
        Purchase.status == "confirmed", Purchase.lesson_id.is_not(None)))).scalars().all())
    sections = []
    for s in secs:
        lessons = (await db.execute(select(Lesson).where(
            Lesson.section_id == s.id, Lesson.deleted_at.is_(None)).order_by(
            Lesson.sort_order))).scalars().all()
        litems = []
        for les in lessons:
            lesson_ok = await payments.lesson_access(db, user, c, les)
            prog = await _lesson_progress(db, user.id, les.id) if lesson_ok else 0
            litems.append({"id": les.id, "title": les.title, "summary": les.summary,
                           "progress": prog, "price_cents": les.price_cents,
                           "locked": not lesson_ok, "purchased": les.id in purchased_lessons})
        sections.append({"id": s.id, "title": s.title, "lessons": litems})
    return envelope(True, "", {"id": c.id, "title": c.title, "summary": c.summary,
                               "visibility": c.visibility, "can_learn": can_learn,
                               "can_edit": staff, "can_price": await _is_staff(db, user, "course/pricing"),
                               "enrolled": await _enrolled(db, user, c.id),
                               "price_cents": c.price_cents, "sections": sections})


# ---- lesson player --------------------------------------------------------
@router.get("/lessons/{lesson_id}")
async def lesson_player(lesson_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    les, sec, c = await payments.require_lesson(db, user, lesson_id)
    items = (await db.execute(select(LessonItem).where(
        LessonItem.lesson_id == les.id).order_by(LessonItem.sort_order))).scalars().all()
    done_ids = {p.item_id for p in (await db.execute(select(LessonProgress).where(
        LessonProgress.user_id == user.id, LessonProgress.lesson_id == les.id))).scalars().all()}
    out = []
    for it in items:
        d = {"id": it.id, "item_type": it.item_type, "title": it.title,
             "body": it.body, "url": it.url, "file_name": it.file_name,
             "completed": it.id in done_ids}
        if it.item_type == "question":
            # options only — the correct answer stays on the server
            d["options"] = it.options_json or []
        out.append(d)
    return envelope(True, "", {"id": les.id, "title": les.title, "course_id": c.id,
                               "course_title": c.title, "progress": await _lesson_progress(db, user.id, les.id),
                               "can_edit": await _is_staff(db, user, "lesson/edit"),
                               "items": out})

@router.post("/lessons/{lesson_id}/items")
async def add_item(lesson_id: int, request: Request,
                   item_type: str = Form(...), title: str = Form(""),
                   body: str = Form(""), url: str = Form(""),
                   options: str = Form(""), correct_index: int = Form(-1),
                   upload: UploadFile | None = File(None),
                   db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "lesson/edit")
    await check_csrf(request, sess)
    les = (await db.execute(select(Lesson).where(
        Lesson.id == lesson_id, Lesson.deleted_at.is_(None)))).scalar_one_or_none()
    if les is None:
        return envelope(False, "err.lesson_not_found")
    if item_type not in ("text", "file", "link", "question"):
        return envelope(False, "err.field_invalid")
    n = (await db.execute(select(func.count(LessonItem.id)).where(
        LessonItem.lesson_id == les.id))).scalar_one()
    screened = await moderation.screen(db, user, {"title": title, "body": body, "options": options}, source="lesson.item", count_strike=False)
    it = LessonItem(lesson_id=les.id, item_type=item_type, title=screened.values["title"][:200],
                    body=screened.values["body"], url=url[:500], sort_order=n)
    if item_type == "file":
        if upload is None:
            return envelope(False, "err.file_required")
        try:
            data = await files.read_upload(upload)
            saved = files.save("lessons", upload.filename or "file", data)
        except files.FileError as e:
            return envelope(False, e.key)
        it.file_path, it.file_name = saved["key"], saved["file_name"]
    if item_type == "question":
        opts = [o.strip() for o in screened.values["options"].splitlines() if o.strip()]
        if len(opts) < 2 or not (0 <= correct_index < len(opts)):
            return envelope(False, "err.field_invalid")
        it.options_json = opts
        it.correct_index = correct_index
    db.add(it)
    await db.flush()
    await db.commit()
    return envelope(True, "lesson.item_added", {"id": it.id})

@router.post("/lesson_items/{item_id}/complete")
async def complete_item(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    it = (await db.execute(select(LessonItem).where(LessonItem.id == item_id))).scalar_one_or_none()
    if it is None:
        return envelope(False, "err.not_found")
    les, sec, c = await payments.require_lesson(db, user, it.lesson_id)
    exists = (await db.execute(select(LessonProgress).where(
        LessonProgress.user_id == user.id, LessonProgress.item_id == it.id))).scalar_one_or_none()
    if exists is None:
        db.add(LessonProgress(user_id=user.id, lesson_id=les.id, item_id=it.id))
        await db.flush()
    await db.commit()
    return envelope(True, "ok.item_completed",
                    {"progress": await _lesson_progress(db, user.id, les.id)})

class AnswerIn(BaseModel):
    choice: int

@router.post("/lesson_items/{item_id}/check")
async def check_answer(item_id: int, body: AnswerIn, request: Request,
                       db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    it = (await db.execute(select(LessonItem).where(LessonItem.id == item_id))).scalar_one_or_none()
    if it is None or it.item_type != "question":
        return envelope(False, "err.not_found")
    await payments.require_lesson(db, user, it.lesson_id)
    correct = (it.correct_index is not None and body.choice == it.correct_index)
    if correct:
        exists = (await db.execute(select(LessonProgress).where(
            LessonProgress.user_id == user.id, LessonProgress.item_id == it.id))).scalar_one_or_none()
        if exists is None:
            db.add(LessonProgress(user_id=user.id, lesson_id=it.lesson_id, item_id=it.id))
            await db.flush()
    await db.commit()
    # never reveal the correct index — only whether the learner was right
    return envelope(True, "lesson.answer_correct" if correct else "lesson.answer_wrong",
                    {"correct": correct})

@router.get("/lesson_items/{item_id}/file")
async def item_file(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import FileResponse
    sess, user = await require_user(request, db)
    it = (await db.execute(select(LessonItem).where(LessonItem.id == item_id))).scalar_one_or_none()
    if it is None or it.item_type != "file" or not it.file_path:
        raise HTTPException(status_code=404, detail="err.not_found")
    les, sec, c = await payments.require_lesson(db, user, it.lesson_id)
    path = files.resolve(it.file_path)
    return FileResponse(path, filename=it.file_name or "file")

@router.post("/lessons/{lesson_id}/complete")
async def complete_lesson(lesson_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    les, sec, c = await payments.require_lesson(db, user, lesson_id)
    exists = (await db.execute(select(LessonProgress).where(
        LessonProgress.user_id == user.id, LessonProgress.lesson_id == les.id,
        LessonProgress.item_id.is_(None)))).scalar_one_or_none()
    if exists is None:
        db.add(LessonProgress(user_id=user.id, lesson_id=les.id, item_id=None))
        await db.flush()
    await db.commit()
    return envelope(True, "lesson.completed", {"progress": 100})
