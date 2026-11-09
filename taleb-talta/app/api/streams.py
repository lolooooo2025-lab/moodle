"""Live stream metadata/player APIs. Publish credentials are owner-only."""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import streams as core, ratelimit
from app.core.audit import audit
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip
from app.models import LiveStream

router = APIRouter(tags=["streams"])


class StreamIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    audience: str = "all"
    course_id: int | None = None
    division_id: int | None = None
    scheduled_at: datetime
    playback_url: str = Field(default="", max_length=2000)
    ingest_url: str = Field(default="", max_length=2000)
    publish_key: str | None = Field(default=None, min_length=8, max_length=512)

class UpdateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    audience: str = "all"
    course_id: int | None = None
    division_id: int | None = None
    scheduled_at: datetime
    playback_url: str = Field(default="", max_length=2000)

class ActionIn(BaseModel):
    action: str = Field(pattern="^(start|end|cancel)$")


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(422, "stream.time_invalid")
    return value.astimezone(timezone.utc)


@router.get("/api/streams")
async def listing(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(LiveStream).where(LiveStream.status != "cancelled")
             .order_by(LiveStream.scheduled_at.desc()).limit(100))).scalars().all()
    out = []
    for row in rows:
        if await core.can_watch(db, user, row):
            out.append(await core.public(db, user, row))
    return envelope(True, "", out)


@router.get("/api/streams/{stream_id}")
async def detail(stream_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    row = await core.get_stream(db, stream_id)
    await core.require_watch(db, user, row)
    return envelope(True, "", await core.public(db, user, row))


@router.get("/api/admin/streams")
async def admin_list(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/manage")
    rows = (await db.execute(select(LiveStream).order_by(LiveStream.scheduled_at.desc()).limit(100))).scalars().all()
    return envelope(True, "", [await core.public(db, user, r, manage=True) for r in rows])


@router.post("/api/admin/streams")
async def create(body: StreamIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/manage")
    await check_csrf(request, sess)
    if not await ratelimit.hit(db, f"stream:{user.id}", 20, 3600):
        await db.commit(); raise HTTPException(429, "err.rate_limited")
    data = body.model_dump(); data["scheduled_at"] = aware(body.scheduled_at)
    row = await core.create(db, user, data, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.created", {"id": row.id})


@router.post("/api/admin/streams/{stream_id}")
async def update(stream_id: int, body: UpdateIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/manage")
    await check_csrf(request, sess)
    row = await core.get_stream(db, stream_id)
    data = body.model_dump(); data["scheduled_at"] = aware(body.scheduled_at)
    await core.update(db, user, row, data, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated")


@router.post("/api/admin/streams/{stream_id}/status")
async def transition(stream_id: int, body: ActionIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/manage")
    await check_csrf(request, sess)
    row = await core.get_stream(db, stream_id)
    await core.transition(db, user, row, body.action, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"status": row.status})


@router.get("/api/admin/streams/{stream_id}/credentials")
async def credentials(stream_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/key")
    if user.role != "owner":
        raise HTTPException(403, "err.forbidden")
    row = await core.get_stream(db, stream_id)
    data = await core.credentials(db, user, row)
    await audit(db, action="stream.key_revealed", actor=user, entity_type="stream", entity_id=row.id,
                ip=client_ip(request), severity="critical")
    await db.commit()
    return envelope(True, "", data)


@router.post("/api/admin/streams/{stream_id}/rotate-key")
async def rotate(stream_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "stream/key")
    await check_csrf(request, sess)
    if user.role != "owner":
        raise HTTPException(403, "err.forbidden")
    row = await core.get_stream(db, stream_id)
    key = await core.rotate_key(db, user, row, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"publish_key": key})
