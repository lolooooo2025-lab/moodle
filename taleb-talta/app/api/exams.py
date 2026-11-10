"""Exams & grading API (Wave 2).

Question bank (6 objective/short types), exams, timed attempts, server-side
grading, gradebook + CSV export, and per-question result discussion. Correct
answers (answer_json) are NEVER serialised to the browser before submission.
"""
from __future__ import annotations
import csv, io, random
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.audit import audit
from app.core.capabilities import tt_can
from app.core import moderation, payments
from app.api.deps import (envelope, require_user, require_cap, client_ip, check_csrf)
from app.api.courses import _get_course, _enrolled, _available
from app.models import (Question, Exam, ExamQuestion, ExamAttempt, AttemptAnswer,
                        QuestionPost, CourseStudent, User, utcnow)

router = APIRouter(prefix="/api", tags=["exams"])
QTYPES = ("mcq_single", "mcq_multi", "truefalse", "short", "match", "numeric")


# ---- helpers --------------------------------------------------------------
async def _exam_staff(db, user) -> bool:
    return await tt_can(db, user, "exam/create")

async def _get_exam(db, exam_id) -> Exam:
    e = (await db.execute(select(Exam).where(
        Exam.id == exam_id, Exam.deleted_at.is_(None)))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="err.exam_not_found")
    return e

async def _get_question(db, question_id) -> Question:
    q = (await db.execute(select(Question).where(
        Question.id == question_id, Question.deleted_at.is_(None)))).scalar_one_or_none()
    if q is None:
        raise HTTPException(status_code=404, detail="err.question_not_found")
    return q

def _exam_available(e: Exam) -> str | None:
    now = utcnow()
    if e.available_from and now < e.available_from:
        return "exam.not_available_yet"
    if e.available_to and now > e.available_to:
        return "exam.not_available_anymore"
    return None

async def _can_take(db, user, e: Exam, course) -> bool:
    if await _exam_staff(db, user):
        return True
    if e.visibility != "visible" or _exam_available(e):
        return False
    return await payments.learn_access(db, user, course)


async def _require_take(db, user, e: Exam):
    course = await _get_course(db, e.course_id)
    if not await _can_take(db, user, e, course):
        raise HTTPException(403, "PAID_CONTENT_LOCKED" if course.price_cents > 0 else "err.not_enrolled")
    return course

async def _require_question_learning(db, user, question: Question):
    if question.course_id and not await _exam_staff(db, user):
        course = await _get_course(db, question.course_id)
        if not await payments.learn_access(db, user, course):
            raise HTTPException(403, "PAID_CONTENT_LOCKED" if course.price_cents > 0 else "err.not_enrolled")


async def _exam_questions(db, exam_id):
    rows = (await db.execute(select(ExamQuestion).where(
        ExamQuestion.exam_id == exam_id).order_by(ExamQuestion.sort_order, ExamQuestion.id))).scalars().all()
    out = []
    for eq in rows:
        q = (await db.execute(select(Question).where(Question.id == eq.question_id))).scalar_one_or_none()
        if q is not None and q.deleted_at is None:
            out.append((eq, q))
    return out

def _grade(qtype: str, answer: dict | None, response: dict | None):
    """Return (is_correct, needs_manual). Short answer is always manual."""
    answer = answer or {}
    response = response or {}
    if qtype == "short":
        return None, True
    if qtype == "mcq_single":
        return response.get("choice") == answer.get("correct"), False
    if qtype == "mcq_multi":
        try:
            return set(response.get("choices", [])) == set(answer.get("correct", [])), False
        except TypeError:
            return False, False
    if qtype == "truefalse":
        return response.get("choice") == answer.get("correct"), False
    if qtype == "numeric":
        try:
            tol = float(answer.get("tolerance", 0) or 0)
            return abs(float(response.get("value")) - float(answer.get("value"))) <= tol, False
        except (TypeError, ValueError):
            return False, False
    if qtype == "match":
        try:
            resp = {tuple(p) for p in response.get("pairs", [])}
            corr = {tuple(p) for p in answer.get("pairs", [])}
            return bool(corr) and resp == corr, False
        except (TypeError, ValueError):
            return False, False
    return False, False

def _validate_question(qtype, prompt, options, answer) -> str | None:
    if qtype not in QTYPES:
        return "err.field_invalid"
    if not (prompt or "").strip():
        return "err.required"
    if qtype in ("mcq_single", "mcq_multi"):
        if not isinstance(options, list) or len(options) < 2:
            return "exam.options_required"
        if not isinstance(answer, dict) or "correct" not in answer:
            return "exam.answer_required"
    elif qtype == "truefalse":
        if not isinstance(answer, dict) or not isinstance(answer.get("correct"), bool):
            return "exam.answer_required"
    elif qtype == "numeric":
        if not isinstance(answer, dict) or "value" not in answer:
            return "exam.answer_required"
    elif qtype == "match":
        if not isinstance(options, dict) or not options.get("left") or not options.get("right"):
            return "exam.options_required"
        if not isinstance(answer, dict) or not answer.get("pairs"):
            return "exam.answer_required"
    return None


# ---- question bank --------------------------------------------------------
class QuestionIn(BaseModel):
    course_id: int | None = None
    qtype: str = "mcq_single"
    prompt: str
    options_json: list | dict | None = None
    answer_json: dict | None = None
    explanation: str = ""

@router.get("/questions")
async def list_questions(request: Request, course_id: int | None = None,
                         db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/create")
    stmt = select(Question).where(Question.deleted_at.is_(None))
    if course_id is not None:
        stmt = stmt.where(Question.course_id == course_id)
    qs = (await db.execute(stmt.order_by(Question.id.desc()))).scalars().all()
    # staff editor may see answers (they author them)
    return envelope(True, "", [{"id": q.id, "course_id": q.course_id, "qtype": q.qtype,
                                "prompt": q.prompt, "options": q.options_json,
                                "answer": q.answer_json, "explanation": q.explanation} for q in qs])

@router.post("/questions")
async def create_question(body: QuestionIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/create")
    await check_csrf(request, sess)
    err = _validate_question(body.qtype, body.prompt, body.options_json, body.answer_json)
    if err:
        return envelope(False, err)
    screened = await moderation.screen(db, user, {"prompt": body.prompt, "explanation": body.explanation},
                                       source="exam.question", ip=client_ip(request), count_strike=False)
    options = body.options_json
    if isinstance(options, list):
        options = [moderation.filter_text(str(v), await moderation.dictionary(db))[0] for v in options]
    elif isinstance(options, dict):
        options = {k: [moderation.filter_text(str(v), await moderation.dictionary(db))[0] for v in vs]
                   for k, vs in options.items()}
    q = Question(course_id=body.course_id, qtype=body.qtype, prompt=screened.values["prompt"].strip(),
                 options_json=options, answer_json=body.answer_json,
                 explanation=screened.values["explanation"], created_by=user.id)
    db.add(q)
    await db.flush()
    await audit(db, action="exam.question_created", actor=user, entity_type="question",
                entity_id=q.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "exam.question_created", {"id": q.id})

@router.post("/questions/{question_id}/delete")
async def delete_question(question_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/create")
    await check_csrf(request, sess)
    q = await _get_question(db, question_id)
    q.deleted_at = utcnow()
    await audit(db, action="exam.question_deleted", actor=user, entity_type="question",
                entity_id=q.id, ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "exam.question_deleted")


# ---- exams ----------------------------------------------------------------
class ExamIn(BaseModel):
    course_id: int
    title: str
    description: str = ""
    time_limit_minutes: int = 0
    max_attempts: int = 1
    visibility: str = "visible"
    shuffle: bool = False

@router.get("/exams")
async def list_exams(request: Request, course_id: int, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    course = await _get_course(db, course_id)
    staff = await _exam_staff(db, user)
    if not staff and not await payments.learn_access(db, user, course):
        raise HTTPException(403, "PAID_CONTENT_LOCKED" if course.price_cents > 0 else "err.not_enrolled")
    stmt = select(Exam).where(Exam.course_id == course_id, Exam.deleted_at.is_(None))
    if not staff:
        stmt = stmt.where(Exam.visibility == "visible")
    exams = (await db.execute(stmt.order_by(Exam.id.desc()))).scalars().all()
    out = []
    for e in exams:
        nq = (await db.execute(select(func.count(ExamQuestion.id)).where(
            ExamQuestion.exam_id == e.id))).scalar_one()
        att = (await db.execute(select(func.count(ExamAttempt.id)).where(
            ExamAttempt.exam_id == e.id, ExamAttempt.user_id == user.id))).scalar_one()
        best = (await db.execute(select(func.max(ExamAttempt.score)).where(
            ExamAttempt.exam_id == e.id, ExamAttempt.user_id == user.id,
            ExamAttempt.status == "graded"))).scalar_one()
        out.append({"id": e.id, "title": e.title, "description": e.description,
                    "time_limit_minutes": e.time_limit_minutes, "max_attempts": e.max_attempts,
                    "visibility": e.visibility, "question_count": nq, "attempts_used": att,
                    "best_score": best, "available": _exam_available(e) is None,
                    "available_key": _exam_available(e) or ""})
    return envelope(True, "", out)

@router.post("/exams")
async def create_exam(body: ExamIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/create")
    await check_csrf(request, sess)
    await _get_course(db, body.course_id)
    if not body.title.strip():
        return envelope(False, "err.required")
    if body.visibility not in ("visible", "hidden"):
        return envelope(False, "err.field_invalid")
    screened = await moderation.screen(db, user, {"title": body.title, "description": body.description},
                                       source="exam.create", count_strike=False)
    e = Exam(course_id=body.course_id, title=screened.values["title"].strip()[:200], description=screened.values["description"],
             time_limit_minutes=max(0, body.time_limit_minutes), max_attempts=max(0, body.max_attempts),
             visibility=body.visibility, shuffle=body.shuffle, created_by=user.id)
    db.add(e)
    await db.flush()
    await audit(db, action="exam.created", actor=user, entity_type="exam",
                entity_id=e.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "exam.created", {"id": e.id})

class ExamQuestionsIn(BaseModel):
    question_id: int
    points: int = 1

@router.post("/exams/{exam_id}/questions")
async def add_exam_question(exam_id: int, body: ExamQuestionsIn, request: Request,
                            db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/create")
    await check_csrf(request, sess)
    e = await _get_exam(db, exam_id)
    await _get_question(db, body.question_id)
    exists = (await db.execute(select(ExamQuestion).where(
        ExamQuestion.exam_id == exam_id, ExamQuestion.question_id == body.question_id))).scalar_one_or_none()
    if exists:
        return envelope(False, "exam.question_already_added")
    n = (await db.execute(select(func.count(ExamQuestion.id)).where(
        ExamQuestion.exam_id == exam_id))).scalar_one()
    db.add(ExamQuestion(exam_id=exam_id, question_id=body.question_id,
                        sort_order=n, points=max(1, body.points)))
    await audit(db, action="exam.question_added", actor=user, entity_type="exam",
                entity_id=e.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "exam.question_added")

@router.get("/exams/{exam_id}")
async def exam_detail(exam_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    e = await _get_exam(db, exam_id)
    course = await _require_take(db, user, e)
    staff = await _exam_staff(db, user)
    pairs = await _exam_questions(db, exam_id)
    qs = []
    for eq, q in pairs:
        item = {"id": q.id, "qtype": q.qtype, "prompt": q.prompt,
                "options": q.options_json, "points": eq.points}
        if staff:                       # only the authoring staff see answers here
            item["answer"] = q.answer_json
            item["explanation"] = q.explanation
        qs.append(item)
    return envelope(True, "", {"id": e.id, "title": e.title, "description": e.description,
                               "course_id": e.course_id, "time_limit_minutes": e.time_limit_minutes,
                               "max_attempts": e.max_attempts, "can_edit": staff, "questions": qs})


# ---- attempts -------------------------------------------------------------
@router.post("/exams/{exam_id}/start")
async def start_attempt(exam_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/take")
    await check_csrf(request, sess)
    await moderation.require_evaluations(db, user)
    e = await _get_exam(db, exam_id)
    course = await _require_take(db, user, e)
    pairs = await _exam_questions(db, exam_id)
    if not pairs:
        return envelope(False, "exam.no_questions")
    now = utcnow()
    # resume an in-progress attempt, or finalise an expired one
    existing = (await db.execute(select(ExamAttempt).where(
        ExamAttempt.exam_id == exam_id, ExamAttempt.user_id == user.id,
        ExamAttempt.status == "in_progress"))).scalar_one_or_none()
    if existing is not None:
        if existing.expires_at is None or now <= existing.expires_at:
            return _attempt_payload(e, existing, pairs)
        existing.status = "graded"
        existing.submitted_at = now
        existing.score = 0
        await db.commit()
    used = (await db.execute(select(func.count(ExamAttempt.id)).where(
        ExamAttempt.exam_id == exam_id, ExamAttempt.user_id == user.id))).scalar_one()
    if e.max_attempts > 0 and used >= e.max_attempts:
        return envelope(False, "exam.no_attempts_left")
    expires = None
    if e.time_limit_minutes > 0:
        from datetime import timedelta
        expires = now + timedelta(minutes=e.time_limit_minutes)
    att = ExamAttempt(exam_id=exam_id, user_id=user.id, attempt_number=used + 1,
                      status="in_progress", expires_at=expires,
                      max_score=sum(eq.points for eq, _ in pairs))
    db.add(att)
    await db.flush()
    await audit(db, action="exam.attempt_started", actor=user, entity_type="exam_attempt",
                entity_id=att.id, ip=client_ip(request))
    await db.commit()
    return _attempt_payload(e, att, pairs)

def _attempt_payload(e: Exam, att: ExamAttempt, pairs):
    order = list(pairs)
    if e.shuffle:
        random.Random(att.id).shuffle(order)
    qs = [{"id": q.id, "qtype": q.qtype, "prompt": q.prompt,
           "options": q.options_json, "points": eq.points} for eq, q in order]
    return envelope(True, "exam.attempt_started", {
        "attempt_id": att.id, "exam_id": e.id, "title": e.title,
        "time_limit_minutes": e.time_limit_minutes,
        "expires_at": att.expires_at.isoformat() if att.expires_at else None,
        "questions": qs})

class SubmitIn(BaseModel):
    answers: dict = {}

@router.post("/attempts/{attempt_id}/submit")
async def submit_attempt(attempt_id: int, body: SubmitIn, request: Request,
                         db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/take")
    await check_csrf(request, sess)
    att = (await db.execute(select(ExamAttempt).where(
        ExamAttempt.id == attempt_id, ExamAttempt.user_id == user.id))).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="err.attempt_not_found")
    if att.status != "in_progress":
        return envelope(False, "exam.already_submitted")
    now = utcnow()
    if att.expires_at is not None and now > att.expires_at:
        return envelope(False, "exam.time_up")
    e = await _get_exam(db, att.exam_id)
    await _require_take(db, user, e)
    pairs = await _exam_questions(db, att.exam_id)
    score = 0.0
    max_score = 0.0
    any_manual = False
    for eq, q in pairs:
        resp = body.answers.get(str(q.id)) or body.answers.get(q.id) or {}
        correct, manual = _grade(q.qtype, q.answer_json, resp)
        pts = float(eq.points) if correct else 0.0
        if manual:
            any_manual = True
        score += pts
        max_score += eq.points
        db.add(AttemptAnswer(attempt_id=att.id, question_id=q.id, response_json=resp,
                             is_correct=correct, points_awarded=pts, needs_manual=manual))
    att.score = score
    att.max_score = max_score
    att.submitted_at = now
    att.status = "submitted" if any_manual else "graded"
    if not any_manual:
        att.graded_at = now
    await audit(db, action="exam.attempt_submitted", actor=user, entity_type="exam_attempt",
                entity_id=att.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "exam.submitted", {"attempt_id": att.id, "score": score,
                                             "max_score": max_score, "status": att.status,
                                             "needs_manual": any_manual})

@router.get("/attempts/{attempt_id}/review")
async def review_attempt(attempt_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    att = (await db.execute(select(ExamAttempt).where(ExamAttempt.id == attempt_id))).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="err.attempt_not_found")
    staff = await tt_can(db, user, "exam/grade")
    if att.user_id != user.id and not staff:
        raise HTTPException(status_code=403, detail="err.forbidden")
    if att.status == "in_progress":
        return envelope(False, "exam.not_submitted_yet")
    pairs = await _exam_questions(db, att.exam_id)
    answers = {a.question_id: a for a in (await db.execute(select(AttemptAnswer).where(
        AttemptAnswer.attempt_id == att.id))).scalars().all()}
    items = []
    for eq, q in pairs:
        a = answers.get(q.id)
        items.append({"id": q.id, "qtype": q.qtype, "prompt": q.prompt, "options": q.options_json,
                      "points": eq.points, "response": a.response_json if a else None,
                      "is_correct": a.is_correct if a else None,
                      "points_awarded": a.points_awarded if a else 0,
                      "needs_manual": a.needs_manual if a else False,
                      "answer": q.answer_json, "explanation": q.explanation})
    return envelope(True, "", {"attempt_id": att.id, "exam_id": att.exam_id, "score": att.score,
                               "max_score": att.max_score, "status": att.status, "items": items})

class ManualGradeIn(BaseModel):
    grades: dict = {}        # question_id -> points awarded

@router.post("/attempts/{attempt_id}/grade")
async def manual_grade(attempt_id: int, body: ManualGradeIn, request: Request,
                       db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "exam/grade")
    await check_csrf(request, sess)
    att = (await db.execute(select(ExamAttempt).where(ExamAttempt.id == attempt_id))).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=404, detail="err.attempt_not_found")
    if att.status not in ("submitted", "graded"):
        return envelope(False, "exam.not_submitted_yet")
    pairs = {q.id: eq for eq, q in await _exam_questions(db, att.exam_id)}
    answers = (await db.execute(select(AttemptAnswer).where(
        AttemptAnswer.attempt_id == att.id, AttemptAnswer.needs_manual.is_(True)))).scalars().all()
    for a in answers:
        raw = body.grades.get(str(a.question_id), body.grades.get(a.question_id))
        if raw is None:
            continue
        maxp = pairs[a.question_id].points if a.question_id in pairs else 1
        pts = max(0.0, min(float(raw), float(maxp)))
        a.points_awarded = pts
        a.is_correct = pts > 0
        a.needs_manual = False
    att.score = sum(a.points_awarded for a in (await db.execute(select(AttemptAnswer).where(
        AttemptAnswer.attempt_id == att.id))).scalars().all())
    att.status = "graded"
    att.graded_by = user.id
    att.graded_at = utcnow()
    await audit(db, action="exam.attempt_graded", actor=user, entity_type="exam_attempt",
                entity_id=att.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "exam.graded", {"attempt_id": att.id, "score": att.score,
                                          "max_score": att.max_score})


# ---- gradebook ------------------------------------------------------------
async def _gradebook_rows(db, course_id):
    exams = (await db.execute(select(Exam).where(
        Exam.course_id == course_id, Exam.deleted_at.is_(None)).order_by(Exam.id))).scalars().all()
    students = (await db.execute(select(User).join(CourseStudent, CourseStudent.user_id == User.id)
                .where(CourseStudent.course_id == course_id).order_by(User.name))).scalars().all()
    rows = []
    for u in students:
        scores = {}
        total = 0.0
        for e in exams:
            best = (await db.execute(select(func.max(ExamAttempt.score)).where(
                ExamAttempt.exam_id == e.id, ExamAttempt.user_id == u.id,
                ExamAttempt.status == "graded"))).scalar_one()
            scores[e.id] = best
            if best is not None:
                total += best
        rows.append({"user_id": u.id, "name": u.name, "phone": u.phone,
                     "scores": scores, "total": total})
    rows.sort(key=lambda r: r["total"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return exams, rows

@router.get("/courses/{course_id}/gradebook")
async def gradebook(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "report/view")
    await _get_course(db, course_id)
    exams, rows = await _gradebook_rows(db, course_id)
    return envelope(True, "", {"exams": [{"id": e.id, "title": e.title} for e in exams],
                               "rows": rows})

@router.get("/courses/{course_id}/gradebook/export")
async def gradebook_export(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "report/view")
    await _get_course(db, course_id)
    exams, rows = await _gradebook_rows(db, course_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "phone"] + [e.title for e in exams] + ["total", "rank"])
    for r in rows:
        w.writerow([r["name"], r["phone"]] + [r["scores"].get(e.id, "") for e in exams]
                   + [r["total"], r["rank"]])
    await audit(db, action="exam.gradebook_exported", actor=user, entity_type="course",
                entity_id=course_id, ip=client_ip(request))
    await db.commit()
    return Response(content=buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="gradebook-{course_id}.csv"'})


# ---- per-question discussion ---------------------------------------------
class PostIn(BaseModel):
    body: str

@router.get("/questions/{question_id}/posts")
async def list_posts(question_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    question = await _get_question(db, question_id)
    await _require_question_learning(db, user, question)
    posts = (await db.execute(select(QuestionPost, User.name).join(User, User.id == QuestionPost.user_id)
                .where(QuestionPost.question_id == question_id, QuestionPost.deleted_at.is_(None))
                .order_by(QuestionPost.id))).all()
    return envelope(True, "", [{"id": p.id, "author": name, "body": p.body,
                                "created_at": p.created_at.isoformat()} for p, name in posts])

@router.post("/questions/{question_id}/posts")
async def add_post(question_id: int, body: PostIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "forum/post")
    await check_csrf(request, sess)
    question = await _get_question(db, question_id)
    await _require_question_learning(db, user, question)
    if not body.body.strip():
        return envelope(False, "err.required")
    await moderation.require_communication(db, user)
    screened = await moderation.screen(db, user, {"body": body.body[:2000]}, source="exam.discussion", ip=client_ip(request))
    p = QuestionPost(question_id=question_id, user_id=user.id, body=screened.values["body"])
    db.add(p)
    await db.flush()
    await audit(db, action="exam.question_posted", actor=user, entity_type="question",
                entity_id=question_id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "exam.post_added", {"id": p.id})
