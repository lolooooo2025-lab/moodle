"""Forum threads, nested replies, subscriptions and question deep links (Wave 3)."""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.audit import audit
from app.core.events import bus
from app.core.capabilities import tt_can
from app.core import moderation, ratelimit
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip
from app.api.courses import _get_course, _can_learn
from app.models import (DiscussionThread, DiscussionPost, ForumSubscription, User,
                        Question, Exam, ExamQuestion, ExamAttempt, Course, utcnow)

router = APIRouter(prefix="/api/forum", tags=["forum"])


async def question_access(db, user, question_id: int):
    q = (await db.execute(select(Question).where(Question.id == question_id,
                       Question.deleted_at.is_(None)))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "err.question_not_found")
    rows = (await db.execute(select(Exam).join(ExamQuestion, ExamQuestion.exam_id == Exam.id)
            .where(ExamQuestion.question_id == q.id, Exam.deleted_at.is_(None)))).scalars().all()
    if await tt_can(db, user, "exam/grade"):
        return q, rows[0] if rows else None
    for exam in rows:
        course = (await db.execute(select(Course).where(Course.id == exam.course_id))).scalar_one()
        if not await _can_learn(db, user, course):
            continue
        attempt = (await db.execute(select(ExamAttempt.id).where(
            ExamAttempt.exam_id == exam.id, ExamAttempt.user_id == user.id,
            ExamAttempt.status.in_(["submitted", "graded"])))).first()
        if attempt:
            return q, exam
    raise HTTPException(403, "forum.submit_exam_first")


async def can_read(db, user, thread) -> bool:
    if thread.deleted_at is not None:
        return await tt_can(db, user, "moderation/review")
    if thread.question_id is not None:
        try:
            await question_access(db, user, thread.question_id)
            return True
        except HTTPException:
            return False
    if thread.course_id is not None:
        course = (await db.execute(select(Course).where(Course.id == thread.course_id))).scalar_one_or_none()
        return course is not None and await _can_learn(db, user, course)
    return True


async def get_thread(db, user, thread_id: int):
    thread = (await db.execute(select(DiscussionThread).where(
        DiscussionThread.id == thread_id))).scalar_one_or_none()
    if thread is None or not await can_read(db, user, thread):
        raise HTTPException(404, "forum.thread_not_found")
    return thread


async def thread_data(db, user, thread):
    author = (await db.execute(select(User.name).where(User.id == thread.created_by))).scalar_one()
    count = (await db.execute(select(func.count(DiscussionPost.id)).where(
        DiscussionPost.thread_id == thread.id, DiscussionPost.deleted_at.is_(None)))).scalar_one()
    sub = (await db.execute(select(ForumSubscription).where(
        ForumSubscription.thread_id == thread.id, ForumSubscription.user_id == user.id))).scalar_one_or_none()
    unread = 0
    if sub:
        unread = (await db.execute(select(func.count(DiscussionPost.id)).where(
            DiscussionPost.thread_id == thread.id, DiscussionPost.id > sub.last_seen_post_id,
            DiscussionPost.deleted_at.is_(None)))).scalar_one()
    return {"id": thread.id, "title": thread.title, "author": author, "course_id": thread.course_id,
            "question_id": thread.question_id, "exam_id": thread.exam_id, "locked": thread.locked,
            "removed": thread.deleted_at is not None, "post_count": count,
            "subscribed": sub is not None, "unread": unread,
            "created_at": thread.created_at.isoformat()}


@router.get("/threads")
async def list_threads(request: Request, course_id: int | None = None,
                       db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(DiscussionThread).where(
        DiscussionThread.deleted_at.is_(None)).order_by(DiscussionThread.id.desc()).limit(100))).scalars().all()
    out = []
    for thread in rows:
        if course_id is not None and thread.course_id != course_id:
            continue
        if await can_read(db, user, thread):
            out.append(await thread_data(db, user, thread))
    return envelope(True, "", out)


class ThreadIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    course_id: int | None = None


async def _check_authoring(db, user, request, course_id=None):
    await moderation.require_communication(db, user)
    if not await ratelimit.hit(db, f"forum:{user.id}", 30, 60):
        await db.commit()
        raise HTTPException(429, "err.rate_limited")
    if course_id is not None:
        course = await _get_course(db, course_id)
        if not await _can_learn(db, user, course):
            raise HTTPException(403, "err.not_enrolled")


@router.post("/threads")
async def create_thread(body: ThreadIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "forum/post")
    await check_csrf(request, sess)
    await _check_authoring(db, user, request, body.course_id)
    result = await moderation.screen(db, user, {"title": body.title, "body": body.body},
                                     source="forum.thread", ip=client_ip(request))
    if not result.values["title"].strip() or not result.values["body"].strip():
        return envelope(False, "err.required")
    thread = DiscussionThread(title=result.values["title"], course_id=body.course_id, created_by=user.id)
    db.add(thread)
    await db.flush()
    post = DiscussionPost(thread_id=thread.id, user_id=user.id, body=result.values["body"],
                          was_filtered=result.matched)
    db.add(post)
    await db.flush()
    db.add(ForumSubscription(thread_id=thread.id, user_id=user.id, last_seen_post_id=post.id))
    await audit(db, action="forum.thread_created", actor=user, entity_type="discussion_thread",
                entity_id=thread.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, result.message_key or "forum.thread_created",
                    {"id": thread.id, "warning": result.message_key, "strikes": result.strikes})


class QuestionThreadIn(BaseModel):
    attempt_id: int | None = None


@router.post("/question/{question_id}")
async def open_question_thread(question_id: int, body: QuestionThreadIn, request: Request,
                               db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "forum/post")
    await check_csrf(request, sess)
    q, exam = await question_access(db, user, question_id)
    thread = (await db.execute(select(DiscussionThread).where(
        DiscussionThread.question_id == question_id))).scalar_one_or_none()
    if thread is None:
        await moderation.require_communication(db, user)
        result = await moderation.screen(db, user, {"body": q.prompt}, source="forum.question",
                                         ip=client_ip(request))
        thread = DiscussionThread(title=q.prompt[:200], question_id=q.id,
                                  exam_id=exam.id if exam else None,
                                  course_id=exam.course_id if exam else q.course_id, created_by=user.id)
        db.add(thread)
        await db.flush()
        db.add(DiscussionPost(thread_id=thread.id, user_id=user.id, body=result.values["body"],
                              was_filtered=result.matched))
        await audit(db, action="forum.question_thread_created", actor=user,
                    entity_type="question", entity_id=q.id, ip=client_ip(request))
        await db.commit()
    return envelope(True, "", {"id": thread.id, "question_id": q.id, "exam_id": thread.exam_id,
                               "attempt_id": body.attempt_id})


@router.get("/threads/{thread_id}")
async def detail(thread_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    thread = await get_thread(db, user, thread_id)
    rows = (await db.execute(select(DiscussionPost, User.name).join(User, User.id == DiscussionPost.user_id)
            .where(DiscussionPost.thread_id == thread.id, DiscussionPost.deleted_at.is_(None))
            .order_by(DiscussionPost.id).limit(500))).all()
    posts = [{"id": p.id, "parent_id": p.parent_id, "author": name, "author_id": p.user_id,
              "body": p.body, "created_at": p.created_at.isoformat()} for p, name in rows]
    data = await thread_data(db, user, thread)
    data.update(posts=posts, can_post=await tt_can(db, user, "forum/post"),
                can_moderate=await tt_can(db, user, "moderation/review"),
                restricted=await moderation.active_restriction(db, user.id) is not None)
    return envelope(True, "", data)


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    parent_id: int | None = None


@router.post("/threads/{thread_id}/posts")
async def reply(thread_id: int, body: ReplyIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "forum/post")
    await check_csrf(request, sess)
    thread = await get_thread(db, user, thread_id)
    if thread.locked and not await tt_can(db, user, "moderation/review"):
        raise HTTPException(403, "forum.locked")
    await _check_authoring(db, user, request)
    if body.parent_id is not None:
        parent = (await db.execute(select(DiscussionPost).where(
            DiscussionPost.id == body.parent_id, DiscussionPost.thread_id == thread.id,
            DiscussionPost.deleted_at.is_(None)))).scalar_one_or_none()
        if parent is None:
            return envelope(False, "forum.reply_not_found")
    result = await moderation.screen(db, user, {"body": body.body}, source="forum.reply", ip=client_ip(request))
    if not result.values["body"].strip():
        return envelope(False, "err.required")
    post = DiscussionPost(thread_id=thread.id, parent_id=body.parent_id, user_id=user.id,
                          body=result.values["body"], was_filtered=result.matched)
    db.add(post)
    await db.flush()
    await audit(db, action="forum.post_created", actor=user, entity_type="discussion_post",
                entity_id=post.id, ip=client_ip(request))
    await db.commit()
    await bus.dispatch("forum.post_created", {"thread_id": thread.id, "post_id": post.id})
    return envelope(True, result.message_key or "forum.post_created",
                    {"id": post.id, "warning": result.message_key, "strikes": result.strikes})


@router.post("/threads/{thread_id}/subscribe")
async def subscribe(thread_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    thread = await get_thread(db, user, thread_id)
    sub = (await db.execute(select(ForumSubscription).where(
        ForumSubscription.thread_id == thread.id, ForumSubscription.user_id == user.id))).scalar_one_or_none()
    enabled = sub is None
    if sub is None:
        db.add(ForumSubscription(thread_id=thread.id, user_id=user.id))
    else:
        await db.delete(sub)
    await db.commit()
    return envelope(True, "forum.subscribed" if enabled else "forum.unsubscribed", {"subscribed": enabled})


@router.post("/threads/{thread_id}/read")
async def mark_read(thread_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    thread = await get_thread(db, user, thread_id)
    sub = (await db.execute(select(ForumSubscription).where(
        ForumSubscription.thread_id == thread.id, ForumSubscription.user_id == user.id))).scalar_one_or_none()
    if sub:
        latest = (await db.execute(select(func.max(DiscussionPost.id)).where(
            DiscussionPost.thread_id == thread.id))).scalar_one() or 0
        sub.last_seen_post_id = max(sub.last_seen_post_id, latest)
        await db.commit()
    return envelope(True, "ok.updated")


class LockIn(BaseModel):
    locked: bool


@router.post("/threads/{thread_id}/lock")
async def lock(thread_id: int, body: LockIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "moderation/review")
    await check_csrf(request, sess)
    thread = await get_thread(db, user, thread_id)
    thread.locked = body.locked
    await audit(db, action="forum.thread_locked" if body.locked else "forum.thread_unlocked",
                actor=user, entity_type="discussion_thread", entity_id=thread.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated")
