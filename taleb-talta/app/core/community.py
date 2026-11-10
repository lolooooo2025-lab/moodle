"""Shared communication ACLs. Never trust a channel/member ID from the client."""
from __future__ import annotations
from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from app.models import (User, Channel, ChannelMember, MessageBlock, Course,
                        CourseStudent, Division, LiveStream, utcnow)
from app.core.capabilities import tt_can


async def is_support(db, user) -> bool:
    return await tt_can(db, user, "moderation/review")


async def blocked_between(db, a: int, b: int) -> bool:
    return (await db.execute(select(MessageBlock.id).where(or_(
        and_(MessageBlock.blocker_id == a, MessageBlock.blocked_id == b),
        and_(MessageBlock.blocker_id == b, MessageBlock.blocked_id == a))))).first() is not None


async def contactable(db, user, target) -> bool:
    if target is None or target.id == user.id or target.status != "active":
        return False
    if await blocked_between(db, user.id, target.id):
        return False
    if await is_support(db, user) or target.role in ("owner", "admin", "moderator", "teacher"):
        return True
    if user.division_id and user.division_id == target.division_id:
        return True
    shared = await db.execute(select(CourseStudent.id).join(
        Course, Course.id == CourseStudent.course_id).where(
        CourseStudent.user_id == user.id, Course.deleted_at.is_(None),
        CourseStudent.course_id.in_(select(CourseStudent.course_id).where(
            CourseStudent.user_id == target.id))))
    return shared.first() is not None


async def membership(db, channel_id: int, user):
    channel = (await db.execute(select(Channel).where(
        Channel.id == channel_id, Channel.deleted_at.is_(None)))).scalar_one_or_none()
    if channel is None:
        raise HTTPException(404, "err.channel_not_found")
    member = (await db.execute(select(ChannelMember).where(
        ChannelMember.channel_id == channel_id, ChannelMember.user_id == user.id))).scalar_one_or_none()
    allowed = member is not None
    if channel.kind == "division":
        allowed = (user.division_id == channel.division_id) or await is_support(db, user)
    if channel.kind == "live":
        from app.core import streams
        stream = (await db.execute(select(LiveStream).where(LiveStream.chat_channel_id == channel.id))).scalar_one_or_none()
        allowed = bool(stream and stream.status != "cancelled" and await streams.can_watch(db, user, stream))
    if not allowed:
        raise HTTPException(403, "err.channel_forbidden")
    if member is None:
        member = ChannelMember(channel_id=channel.id, user_id=user.id)
        db.add(member)
        await db.flush()
    return channel, member


async def ensure_division_channels(db):
    """Idempotent backfill for existing users; registration calls this too."""
    divisions = (await db.execute(select(Division))).scalars().all()
    users = (await db.execute(select(User).where(User.status == "active"))).scalars().all()
    for division in divisions:
        channel = (await db.execute(select(Channel).where(
            Channel.kind == "division", Channel.division_id == division.id))).scalar_one_or_none()
        if channel is None:
            owner = next((u for u in users if u.role == "owner"), None)
            if owner is None:
                continue
            channel = Channel(kind="division", title=division.name, division_id=division.id,
                              created_by=owner.id)
            db.add(channel)
            await db.flush()
        for user in users:
            if user.division_id != division.id and user.role not in ("owner", "admin", "moderator"):
                continue
            exists = (await db.execute(select(ChannelMember.id).where(
                ChannelMember.channel_id == channel.id, ChannelMember.user_id == user.id))).first()
            if exists is None:
                db.add(ChannelMember(channel_id=channel.id, user_id=user.id))
    await db.flush()


async def add_division_member(db, user):
    if user.division_id is None:
        return
    channel = (await db.execute(select(Channel).where(
        Channel.kind == "division", Channel.division_id == user.division_id))).scalar_one_or_none()
    if channel is None:
        return
    exists = (await db.execute(select(ChannelMember.id).where(
        ChannelMember.channel_id == channel.id, ChannelMember.user_id == user.id))).first()
    if exists is None:
        db.add(ChannelMember(channel_id=channel.id, user_id=user.id))
        await db.flush()
