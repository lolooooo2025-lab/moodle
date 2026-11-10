"""Private/group/division chat, contacts, read state, blocking and private files.

Messages and 1:1 chat share one authorised channel model. Poll with after_id;
no WebSockets or long-running request is needed. Every history/file/send request
rechecks membership on the server. Uploads are never public static assets.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_, and_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core.db import get_db
from app.core import files, moderation, ratelimit, community, streams
from app.core.audit import audit
from app.core.events import bus
from app.core.auth import normalize_phone
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip
from app.models import (User, Channel, ChannelMember, DirectContact, MessageBlock,
                        Attachment, ChatMessage, Sticker, LiveStream, utcnow)

router = APIRouter(prefix="/api", tags=["chat"])


async def _peer(db, channel, user):
    if channel.kind != "private":
        return None
    row = (await db.execute(select(User).join(ChannelMember, ChannelMember.user_id == User.id)
            .where(ChannelMember.channel_id == channel.id, User.id != user.id))).scalar_one_or_none()
    return row


async def _channel_data(db, user, channel, member):
    peer = await _peer(db, channel, user)
    last = (await db.execute(select(ChatMessage).where(ChatMessage.channel_id == channel.id,
                       ChatMessage.deleted_at.is_(None)).order_by(ChatMessage.id.desc()))).scalars().first()
    unread = (await db.execute(select(func.count(ChatMessage.id)).where(
        ChatMessage.channel_id == channel.id, ChatMessage.id > member.last_read_message_id,
        ChatMessage.sender_id != user.id, ChatMessage.deleted_at.is_(None)))).scalar_one()
    blocked = await community.blocked_between(db, user.id, peer.id) if peer else False
    blocked_by_me = False
    peer_last_read_id = 0
    if peer:
        blocked_by_me = (await db.execute(select(MessageBlock.id).where(
            MessageBlock.blocker_id == user.id, MessageBlock.blocked_id == peer.id))).first() is not None
        peer_member = (await db.execute(select(ChannelMember).where(
            ChannelMember.channel_id == channel.id, ChannelMember.user_id == peer.id))).scalar_one_or_none()
        peer_last_read_id = peer_member.last_read_message_id if peer_member else 0
    members = (await db.execute(select(User.id, User.name).join(ChannelMember, ChannelMember.user_id == User.id)
               .where(ChannelMember.channel_id == channel.id).order_by(User.name))).all()
    can_send = True
    if channel.kind == "live":
        stream = (await db.execute(select(LiveStream).where(LiveStream.chat_channel_id == channel.id))).scalar_one_or_none()
        can_send = bool(stream and stream.status == "live")
    return {"id": channel.id, "kind": channel.kind, "can_send": can_send,
            "title": peer.name if peer else channel.title, "peer_id": peer.id if peer else None,
            "division_id": channel.division_id, "unread": unread, "blocked": blocked,
            "blocked_by_me": blocked_by_me, "peer_last_read_id": peer_last_read_id,
            "members": [{"id": uid, "name": name} for uid, name in members],
            "can_add": channel.kind == "group" and channel.created_by == user.id,
            "last_message": (last.body if last.body else "") if last else "",
            "last_id": last.id if last else 0}


@router.get("/chat/channels")
async def channels(request: Request, kind: str = "", db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(Channel, ChannelMember).join(
        ChannelMember, ChannelMember.channel_id == Channel.id).where(
        ChannelMember.user_id == user.id, Channel.deleted_at.is_(None)))).all()
    out = []
    for channel, member in rows:
        if kind and channel.kind != kind:
            continue
        if channel.kind == "division" and user.division_id != channel.division_id:
            if not await community.is_support(db, user):
                continue
        if channel.kind == "live":
            stream = (await db.execute(select(LiveStream).where(LiveStream.chat_channel_id == channel.id))).scalar_one_or_none()
            if not stream or stream.status == "cancelled" or not await streams.can_watch(db, user, stream):
                continue
        out.append(await _channel_data(db, user, channel, member))
    out.sort(key=lambda c: (c["kind"] == "division", c["last_id"]), reverse=True)
    return envelope(True, "", out)


async def _contact_rows(db, user):
    rows = (await db.execute(select(DirectContact, User).join(User, User.id == DirectContact.contact_id)
            .where(DirectContact.user_id == user.id).order_by(User.name))).all()
    return [{"user_id": u.id, "name": u.name, "role": u.role, "channel_id": c.channel_id,
             "blocked": await community.blocked_between(db, user.id, u.id)} for c, u in rows]


@router.get("/messages/contacts")
async def contacts(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    return envelope(True, "", await _contact_rows(db, user))


@router.get("/messages/find")
async def find_contact(request: Request, phone: str = "", db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "message/send")
    phone = normalize_phone(phone)
    target = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if not await community.contactable(db, user, target):
        raise HTTPException(404, "err.user_not_found")
    return envelope(True, "", {"user_id": target.id, "name": target.name, "role": target.role})


async def _add_contact(db, user, target, channel):
    for a, b in ((user.id, target.id), (target.id, user.id)):
        exists = (await db.execute(select(DirectContact).where(
            DirectContact.user_id == a, DirectContact.contact_id == b))).scalar_one_or_none()
        if exists is None:
            db.add(DirectContact(user_id=a, contact_id=b, channel_id=channel.id))


class StartIn(BaseModel):
    user_id: int


@router.post("/messages/start")
async def start_private(body: StartIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "message/send")
    await check_csrf(request, sess)
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if not await community.contactable(db, user, target):
        raise HTTPException(404, "err.user_not_found")
    contact = (await db.execute(select(DirectContact).where(
        DirectContact.user_id == user.id, DirectContact.contact_id == target.id))).scalar_one_or_none()
    if contact:
        return envelope(True, "", {"channel_id": contact.channel_id})
    channel = Channel(kind="private", created_by=user.id)
    db.add(channel)
    await db.flush()
    db.add_all([ChannelMember(channel_id=channel.id, user_id=user.id),
                ChannelMember(channel_id=channel.id, user_id=target.id)])
    await _add_contact(db, user, target, channel)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        contact = (await db.execute(select(DirectContact).where(
            DirectContact.user_id == user.id, DirectContact.contact_id == target.id))).scalar_one()
        return envelope(True, "", {"channel_id": contact.channel_id})
    return envelope(True, "chat.conversation_ready", {"channel_id": channel.id})


class GroupIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    member_ids: list[int] = Field(min_length=1, max_length=49)


@router.post("/chat/groups")
async def create_group(body: GroupIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "chat/send")
    await check_csrf(request, sess)
    await moderation.require_communication(db, user)
    result = await moderation.screen(db, user, {"title": body.title}, source="chat.group", ip=client_ip(request))
    ids = set(body.member_ids) - {user.id}
    if not ids:
        return envelope(False, "chat.members_required")
    targets = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    if len(targets) != len(ids):
        raise HTTPException(403, "chat.member_forbidden")
    for target in targets:
        if not await community.contactable(db, user, target):
            raise HTTPException(403, "chat.member_forbidden")
    channel = Channel(kind="group", title=result.values["title"], created_by=user.id)
    db.add(channel)
    await db.flush()
    for uid in ids | {user.id}:
        db.add(ChannelMember(channel_id=channel.id, user_id=uid))
    await audit(db, action="chat.group_created", actor=user, entity_type="channel",
                entity_id=channel.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, result.message_key or "chat.group_created", {"channel_id": channel.id})


class MembersIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=49)


@router.post("/chat/channels/{channel_id}/members")
async def add_members(channel_id: int, body: MembersIn, request: Request,
                      db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "chat/send")
    await check_csrf(request, sess)
    channel, _ = await community.membership(db, channel_id, user)
    if channel.kind != "group" or channel.created_by != user.id:
        raise HTTPException(403, "err.forbidden")
    count = (await db.execute(select(func.count(ChannelMember.id)).where(
        ChannelMember.channel_id == channel.id))).scalar_one()
    if count + len(set(body.user_ids)) > 50:
        return envelope(False, "chat.group_limit")
    for uid in set(body.user_ids):
        target = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if not await community.contactable(db, user, target):
            raise HTTPException(403, "chat.member_forbidden")
        exists = (await db.execute(select(ChannelMember).where(
            ChannelMember.channel_id == channel.id, ChannelMember.user_id == uid))).first()
        if exists is None:
            db.add(ChannelMember(channel_id=channel.id, user_id=uid))
    await audit(db, action="chat.members_added", actor=user, entity_type="channel",
                entity_id=channel.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "chat.members_added")


def _attachment_data(a):
    return {"id": a.id, "name": a.file_name, "mime": a.mime, "size": a.file_size,
            "url": "/api/chat/attachments/" + str(a.id) + "/file"}


def _message_data(m, name, attachment=None, sticker=None):
    return {"id": m.id, "channel_id": m.channel_id, "sender_id": m.sender_id, "author": name,
            "body": m.body, "created_at": m.created_at.isoformat(),
            "attachment": _attachment_data(attachment) if attachment else None,
            "sticker": {"id": sticker.id, "title": sticker.title,
                        "url": "/api/stickers/" + str(sticker.id) + "/file"} if sticker else None}


@router.get("/chat/channels/{channel_id}/messages")
async def history(channel_id: int, request: Request, after_id: int = 0, before_id: int = 0,
                  limit: int = 50, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    channel, member = await community.membership(db, channel_id, user)
    await db.commit()
    stmt = select(ChatMessage, User.name).join(User, User.id == ChatMessage.sender_id).where(
        ChatMessage.channel_id == channel.id, ChatMessage.deleted_at.is_(None))
    if after_id:
        stmt = stmt.where(ChatMessage.id > after_id).order_by(ChatMessage.id).limit(min(max(limit, 1), 100))
    else:
        if before_id:
            stmt = stmt.where(ChatMessage.id < before_id)
        stmt = stmt.order_by(ChatMessage.id.desc()).limit(min(max(limit, 1), 100))
    rows = (await db.execute(stmt)).all()
    if not after_id:
        rows.reverse()
    out = []
    for m, name in rows:
        a = (await db.execute(select(Attachment).where(Attachment.id == m.attachment_id))).scalar_one_or_none() if m.attachment_id else None
        st = (await db.execute(select(Sticker).where(Sticker.id == m.sticker_id))).scalar_one_or_none() if m.sticker_id else None
        out.append(_message_data(m, name, a, st))
    return envelope(True, "", {"messages": out, "channel": await _channel_data(db, user, channel, member),
                               "has_more": len(out) == min(max(limit, 1), 100) and not after_id})


async def _quota(db, user_id, size):
    # Serialise quota checks for this user until the upload transaction commits.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext("chat-quota:" + str(user_id)))))
    used = (await db.execute(select(func.coalesce(func.sum(Attachment.file_size), 0)).where(
        Attachment.owner_id == user_id))).scalar_one()
    if used + size > config.CHAT_UPLOAD_QUOTA_BYTES:
        raise HTTPException(403, "err.storage_quota")


@router.post("/chat/attachments")
async def upload_attachment(request: Request, upload: UploadFile = File(...),
                            db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "chat/send")
    await check_csrf(request, sess)
    await moderation.require_communication(db, user)
    if not await ratelimit.hit(db, f"chat_upload:{user.id}", 20, 3600):
        await db.commit()
        return envelope(False, "err.rate_limited")
    try:
        data = await files.read_upload(upload)
        await _quota(db, user.id, len(data))
        saved = files.save("chat", upload.filename or "file", data)
    except files.FileError as e:
        return envelope(False, e.key)
    a = Attachment(owner_id=user.id, purpose="chat", file_path=saved["key"],
                   file_name=saved["file_name"], file_size=saved["file_size"],
                   mime=saved["mime"], sha256=saved["sha256"])
    db.add(a)
    await db.flush()
    await audit(db, action="chat.attachment_uploaded", actor=user, entity_type="attachment",
                entity_id=a.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "chat.attachment_uploaded", _attachment_data(a))


@router.get("/chat/attachments/{attachment_id}/file")
async def attachment_file(attachment_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    a = (await db.execute(select(Attachment).where(Attachment.id == attachment_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "err.not_found")
    message = (await db.execute(select(ChatMessage).where(
        ChatMessage.attachment_id == a.id, ChatMessage.deleted_at.is_(None)))).scalar_one_or_none()
    allowed = a.owner_id == user.id
    if message:
        try:
            await community.membership(db, message.channel_id, user)
            allowed = True
        except HTTPException:
            pass
    if not allowed:
        raise HTTPException(403, "err.forbidden")
    await db.commit()
    try:
        path = files.resolve(a.file_path)
    except files.FileError:
        raise HTTPException(404, "err.not_found")
    return files.gateway(path, a.file_name, a.mime, inline=True)


class SendIn(BaseModel):
    body: str = Field(default="", max_length=4000)
    attachment_id: int | None = None
    sticker_id: int | None = None


@router.post("/chat/channels/{channel_id}/messages")
async def send(channel_id: int, body: SendIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "chat/send")
    await check_csrf(request, sess)
    channel, member = await community.membership(db, channel_id, user)
    if channel.kind == "live":
        stream = (await db.execute(select(LiveStream).where(LiveStream.chat_channel_id == channel.id))).scalar_one_or_none()
        if stream is None or stream.status != "live":
            raise HTTPException(409, "stream.not_live")
    await moderation.require_communication(db, user)
    peer = await _peer(db, channel, user)
    if peer and await community.blocked_between(db, user.id, peer.id):
        raise HTTPException(403, "chat.blocked")
    if not body.body.strip() and body.attachment_id is None and body.sticker_id is None:
        return envelope(False, "chat.content_required")
    if not await ratelimit.hit(db, f"chat:{user.id}", 60, 60) or not await ratelimit.hit(db, f"chat_ip:{client_ip(request)}", 180, 60):
        await db.commit()
        return envelope(False, "err.rate_limited")
    result = await moderation.screen(db, user, {"body": body.body}, source="chat.message", ip=client_ip(request))
    a = None
    if body.attachment_id is not None:
        a = (await db.execute(select(Attachment).where(Attachment.id == body.attachment_id,
                           Attachment.owner_id == user.id, Attachment.purpose == "chat"))).scalar_one_or_none()
        if a is None or (await db.execute(select(ChatMessage.id).where(
                ChatMessage.attachment_id == a.id))).first():
            return envelope(False, "chat.attachment_invalid")
    st = None
    if body.sticker_id is not None:
        st = (await db.execute(select(Sticker).where(Sticker.id == body.sticker_id,
                           Sticker.status == "approved"))).scalar_one_or_none()
        if st is None:
            raise HTTPException(403, "sticker.not_approved")
    m = ChatMessage(channel_id=channel.id, sender_id=user.id, body=result.values["body"],
                    attachment_id=a.id if a else None, sticker_id=st.id if st else None,
                    was_filtered=result.matched)
    db.add(m)
    await db.flush()
    member.last_read_message_id = max(member.last_read_message_id, m.id)
    if peer:
        await _add_contact(db, user, peer, channel)
    await audit(db, action="chat.message_sent", actor=user, entity_type="chat_message",
                entity_id=m.id, ip=client_ip(request))
    await db.commit()
    await bus.dispatch("message.sent", {"message_id": m.id, "channel_id": channel.id, "sender_id": user.id})
    return envelope(True, result.message_key or "ok.sent",
                    {"message": _message_data(m, user.name, a, st), "warning": result.message_key})


class ReadIn(BaseModel):
    message_id: int


@router.post("/chat/channels/{channel_id}/read")
async def read(channel_id: int, body: ReadIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    channel, member = await community.membership(db, channel_id, user)
    exists = (await db.execute(select(ChatMessage.id).where(
        ChatMessage.id == body.message_id, ChatMessage.channel_id == channel.id))).first()
    if exists is None:
        return envelope(False, "err.not_found")
    member.last_read_message_id = max(member.last_read_message_id, body.message_id)
    await db.commit()
    return envelope(True, "msg.read")


class ContactIn(BaseModel):
    user_id: int


@router.post("/messages/block")
async def block(body: ContactIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    if body.user_id == user.id or (await db.execute(select(User.id).where(User.id == body.user_id))).first() is None:
        return envelope(False, "err.user_not_found")
    exists = (await db.execute(select(MessageBlock).where(
        MessageBlock.blocker_id == user.id, MessageBlock.blocked_id == body.user_id))).first()
    if exists is None:
        db.add(MessageBlock(blocker_id=user.id, blocked_id=body.user_id))
    await audit(db, action="message.blocked", actor=user, entity_type="user",
                entity_id=body.user_id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "chat.blocked_ok")


@router.post("/messages/unblock")
async def unblock(body: ContactIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    row = (await db.execute(select(MessageBlock).where(
        MessageBlock.blocker_id == user.id, MessageBlock.blocked_id == body.user_id))).scalar_one_or_none()
    if row:
        await db.delete(row)
    await audit(db, action="message.unblocked", actor=user, entity_type="user",
                entity_id=body.user_id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "chat.unblocked")
