"""Live metadata, audience ACLs and owner-only encrypted publish credentials.

The app hosts the player/chat and stores ingest credentials; it does not pretend
to transcode video. An external RTMPS/HLS encoder is still required.
"""
from __future__ import annotations
import base64, hashlib, hmac, secrets
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select
from cryptography.fernet import Fernet, InvalidToken
from app import config
from app.core import payments
from app.core.audit import audit
from app.models import LiveStream, Channel, Course, Division, User, utcnow

AUDIENCES = ("all", "course", "division")


def _fernet():
    key = base64.urlsafe_b64encode(hmac.new(config.STREAM_SECRET.encode(),
                                          b"taleb-talta:stream-credentials:v1", hashlib.sha256).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return "fernet-v1:" + _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("fernet-v1:"):
        raise ValueError("invalid credential envelope")
    return _fernet().decrypt(value[10:].encode()).decode()


def new_key() -> str:
    return secrets.token_urlsafe(32)


def playback_url(value: str) -> str:
    try:
        p = urlparse(value)
        port = p.port
        valid = (p.scheme == "https" and p.hostname and not p.username and not p.password
                 and not p.fragment and port in (None, 443) and len(value) <= 2000
                 and value == value.strip() and not any(ord(c) < 32 for c in value)
                 and p.path.lower().endswith((".m3u8", ".mpd", ".mp4")))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "stream.playback_invalid")
    return value


def ingest_url(value: str) -> str:
    if not value:
        return ""
    try:
        p = urlparse(value)
        valid = (p.scheme in ("rtmps", "srt", "https") and p.hostname and not p.username
                 and not p.password and not p.fragment and len(value) <= 2000
                 and value == value.strip() and not any(ord(c) < 32 for c in value))
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "stream.ingest_invalid")
    return value


async def validate_audience(db, audience: str, course_id: int | None, division_id: int | None):
    if audience not in AUDIENCES:
        raise HTTPException(422, "stream.audience_invalid")
    if audience == "course":
        if not course_id or not (await db.execute(select(Course.id).where(Course.id == course_id,
                Course.deleted_at.is_(None)))).first():
            raise HTTPException(422, "stream.audience_invalid")
    elif course_id:
        raise HTTPException(422, "stream.audience_invalid")
    if audience == "division":
        if not division_id or not (await db.execute(select(Division.id).where(Division.id == division_id))).first():
            raise HTTPException(422, "stream.audience_invalid")
    elif division_id:
        raise HTTPException(422, "stream.audience_invalid")


async def get_stream(db, stream_id: int) -> LiveStream:
    row = (await db.execute(select(LiveStream).where(LiveStream.id == stream_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "stream.not_found")
    return row


async def can_watch(db, user, stream: LiveStream) -> bool:
    if user.status != "active":
        return False
    if user.role in ("owner", "admin"):
        return True
    if stream.audience == "all":
        return True
    if stream.audience == "division":
        return user.division_id == stream.division_id
    course = (await db.execute(select(Course).where(Course.id == stream.course_id,
                Course.deleted_at.is_(None)))).scalar_one_or_none()
    return bool(course and await payments.learn_access(db, user, course))


async def require_watch(db, user, stream: LiveStream):
    if stream.status == "cancelled" or not await can_watch(db, user, stream):
        raise HTTPException(403, "stream.forbidden")


async def create(db, actor, data: dict, *, ip="") -> LiveStream:
    from app.core import moderation
    await validate_audience(db, data.get("audience", "all"), data.get("course_id"), data.get("division_id"))
    screened = await moderation.screen(db, actor, {"title": data["title"], "description": data.get("description", "")},
                                       source="stream.create", count_strike=False)
    key = data.get("publish_key") or new_key()
    if not 8 <= len(key) <= 512:
        raise HTTPException(422, "stream.key_invalid")
    row = LiveStream(title=screened.values["title"].strip()[:200], description=screened.values["description"],
                     audience=data.get("audience", "all"), course_id=data.get("course_id"),
                     division_id=data.get("division_id"), scheduled_at=data["scheduled_at"],
                     playback_url=playback_url(data.get("playback_url", "")) if data.get("playback_url") else "",
                     ingest_url_encrypted=encrypt(ingest_url(data.get("ingest_url", ""))),
                     publish_key_encrypted=encrypt(key), created_by=actor.id)
    if not row.title:
        raise HTTPException(422, "err.required")
    db.add(row); await db.flush()
    channel = Channel(kind="live", title=row.title, created_by=actor.id)
    db.add(channel); await db.flush()
    row.chat_channel_id = channel.id
    await audit(db, action="stream.created", actor=actor, entity_type="stream", entity_id=row.id,
                after={"audience": row.audience, "scheduled_at": row.scheduled_at.isoformat()}, ip=ip, severity="notice")
    return row


async def update(db, actor, stream: LiveStream, data: dict, *, ip=""):
    stream = (await db.execute(select(LiveStream).where(LiveStream.id == stream.id).with_for_update())).scalar_one()
    if stream.status in ("ended", "cancelled"):
        raise HTTPException(409, "stream.not_editable")
    audience = data.get("audience", stream.audience)
    course_id = data.get("course_id", stream.course_id)
    division_id = data.get("division_id", stream.division_id)
    if stream.status != "scheduled" and (audience, course_id, division_id) != (stream.audience, stream.course_id, stream.division_id):
        raise HTTPException(409, "stream.audience_locked")
    await validate_audience(db, audience, course_id, division_id)
    from app.core import moderation
    screened = await moderation.screen(db, actor, {"title": data.get("title", stream.title),
                                       "description": data.get("description", stream.description)},
                                       source="stream.update", count_strike=False)
    stream.title, stream.description = screened.values["title"].strip()[:200], screened.values["description"]
    if not stream.title:
        raise HTTPException(422, "err.required")
    stream.audience, stream.course_id, stream.division_id = audience, course_id, division_id
    if "scheduled_at" in data and stream.status == "scheduled":
        stream.scheduled_at = data["scheduled_at"]
    if "playback_url" in data:
        stream.playback_url = playback_url(data["playback_url"]) if data["playback_url"] else ""
    stream.updated_at = utcnow()
    channel = (await db.execute(select(Channel).where(Channel.id == stream.chat_channel_id))).scalar_one_or_none()
    if channel:
        channel.title = stream.title
    await audit(db, action="stream.updated", actor=actor, entity_type="stream", entity_id=stream.id,
                after={"audience": stream.audience, "status": stream.status}, ip=ip)


async def transition(db, actor, stream: LiveStream, action: str, *, ip=""):
    stream = (await db.execute(select(LiveStream).where(LiveStream.id == stream.id).with_for_update())).scalar_one()
    allowed = {"start": ("scheduled",), "end": ("live",), "cancel": ("scheduled", "live")}
    if action not in allowed or stream.status not in allowed[action]:
        raise HTTPException(409, "stream.transition_invalid")
    if action == "start":
        if not stream.playback_url:
            raise HTTPException(422, "stream.playback_required")
        stream.status, stream.started_at = "live", utcnow()
    elif action == "end":
        stream.status, stream.ended_at = "ended", utcnow()
    else:
        stream.status, stream.ended_at = "cancelled", utcnow()
    stream.updated_at = utcnow()
    await audit(db, action="stream." + action, actor=actor, entity_type="stream", entity_id=stream.id,
                after={"status": stream.status}, ip=ip, severity="notice")


async def public(db, user, stream: LiveStream, *, manage=False):
    watch = await can_watch(db, user, stream)
    from app.core.capabilities import tt_can
    can_chat = watch and stream.status == "live" and await tt_can(db, user, "chat/send")
    course_title = division_title = ""
    if stream.course_id:
        course_title = (await db.execute(select(Course.title).where(Course.id == stream.course_id))).scalar_one_or_none() or ""
    if stream.division_id:
        division_title = (await db.execute(select(Division.name).where(Division.id == stream.division_id))).scalar_one_or_none() or ""
    data = {"id": stream.id, "title": stream.title, "description": stream.description,
            "audience": stream.audience, "course_id": stream.course_id, "division_id": stream.division_id,
            "course_title": course_title, "division_title": division_title,
            "scheduled_at": stream.scheduled_at.isoformat(), "status": stream.status,
            "started_at": stream.started_at.isoformat() if stream.started_at else "",
            "ended_at": stream.ended_at.isoformat() if stream.ended_at else "",
            "chat_channel_id": stream.chat_channel_id, "can_watch": watch and stream.status != "cancelled",
            "can_chat": can_chat,
            "playback_url": stream.playback_url if (manage or (watch and stream.status == "live")) else ""}
    if manage:
        data["has_publish_key"] = bool(stream.publish_key_encrypted)
        data["has_ingest_url"] = bool(stream.ingest_url_encrypted)
    return data


async def credentials(db, user, stream: LiveStream):
    # Role check is deliberately stricter than a grantable capability: only the owner.
    if user.role != "owner":
        raise HTTPException(403, "err.forbidden")
    return {"publish_key": decrypt(stream.publish_key_encrypted), "ingest_url": decrypt(stream.ingest_url_encrypted)}


async def rotate_key(db, actor, stream: LiveStream, *, ip=""):
    if actor.role != "owner":
        raise HTTPException(403, "err.forbidden")
    stream = (await db.execute(select(LiveStream).where(LiveStream.id == stream.id).with_for_update())).scalar_one()
    if stream.status in ("ended", "cancelled"):
        raise HTTPException(409, "stream.not_editable")
    key = new_key()
    stream.publish_key_encrypted, stream.updated_at = encrypt(key), utcnow()
    await audit(db, action="stream.key_rotated", actor=actor, entity_type="stream", entity_id=stream.id,
                ip=ip, severity="critical")
    return key
