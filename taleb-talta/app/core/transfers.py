"""Chunked browser uploads and short-lived signed download tickets.

The browser protocol keeps every Netlify request below the buffered payload
limit while preserving the application's original 25 MB file policy.  Final
validation still happens in app.core.files.validate, and the original API
still enforces its own capability, moderation, quota and CSRF checks.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select, delete, func

from app import config
from app.core.db import get_sessionmaker
from app.models import UploadTransfer, UploadChunk, StoredObject, utcnow

UPLOAD_CHUNK_BYTES = 3 * 1024 * 1024
MAX_PENDING_PER_USER = 4
TRANSFER_TTL_MINUTES = 60
TICKET_TTL_SECONDS = 300
DIRECT_RESPONSE_BYTES = 15 * 1024 * 1024
RANGE_RESPONSE_BYTES = 4 * 1024 * 1024
MANIFEST_MAGIC = "tt-transfer-v1"
STATUS_OPEN = "open"
STATUS_READY = "ready"


def _ticket_key() -> bytes:
    return hmac.new(config.SESSION_SECRET.encode(), b"taleb-talta:file-ticket:v1",
                    hashlib.sha256).digest()


def sign_ticket(key: str, name: str, mime: str, inline: bool) -> str:
    payload = {"k": key, "n": name, "m": mime, "i": bool(inline),
               "e": int(utcnow().timestamp()) + TICKET_TTL_SECONDS,
               "r": secrets.token_hex(8)}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_ticket_key(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_ticket(ticket: str) -> dict:
    try:
        raw, sig = ticket.rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(_ticket_key(), raw.encode(), hashlib.sha256).hexdigest(), sig):
            raise ValueError("signature")
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if int(payload["e"]) < int(utcnow().timestamp()):
            raise ValueError("expired")
        if not isinstance(payload["k"], str) or not payload["k"]:
            raise ValueError("key")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(403, "err.forbidden")


def download_url(key: str, name: str, mime: str, *, inline: bool) -> str:
    return "/api/files/content?" + urlencode({"ticket": sign_ticket(key, name, mime, inline)})


async def create_transfer(db, owner_id: int, *, filename: str, size: int, sha256: str) -> UploadTransfer:
    from app.core.files import MAX_BYTES, _ext, ALLOWED
    if size < 1 or size > MAX_BYTES:
        raise HTTPException(413, "err.upload_size")
    if _ext(filename) not in ALLOWED:
        raise HTTPException(422, "err.upload_type")
    if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256.lower()):
        raise HTTPException(422, "err.field_invalid")
    pending = (await db.execute(select(func.count()).select_from(UploadTransfer).where(
        UploadTransfer.owner_id == owner_id, UploadTransfer.expires_at > utcnow()))).scalar_one()
    if pending >= MAX_PENDING_PER_USER:
        raise HTTPException(429, "err.rate_limited")
    row = UploadTransfer(id=secrets.token_hex(24), owner_id=owner_id,
                         filename=filename[:255], size=size, sha256=sha256.lower(),
                         chunk_count=(size + UPLOAD_CHUNK_BYTES - 1) // UPLOAD_CHUNK_BYTES,
                         status=STATUS_OPEN, created_at=utcnow(),
                         expires_at=utcnow() + timedelta(minutes=TRANSFER_TTL_MINUTES))
    db.add(row)
    await db.flush()
    return row


async def add_chunk(db, owner_id: int, transfer_id: str, index: int, data: bytes):
    row = (await db.execute(select(UploadTransfer).where(
        UploadTransfer.id == transfer_id, UploadTransfer.owner_id == owner_id))).scalar_one_or_none()
    if row is None or row.status != STATUS_OPEN or row.expires_at <= utcnow():
        raise HTTPException(404, "err.not_found")
    if index < 0 or index >= row.chunk_count or not data:
        raise HTTPException(422, "err.field_invalid")
    expected = min(UPLOAD_CHUNK_BYTES, row.size - index * UPLOAD_CHUNK_BYTES)
    if len(data) != expected:
        raise HTTPException(422, "err.field_invalid")
    exists = (await db.execute(select(UploadChunk.id).where(
        UploadChunk.transfer_id == transfer_id, UploadChunk.index == index))).first()
    if exists:
        raise HTTPException(409, "err.already_exists")
    db.add(UploadChunk(transfer_id=transfer_id, index=index, data=data))
    await db.flush()


async def complete_transfer(db, owner_id: int, transfer_id: str) -> dict:
    row = (await db.execute(select(UploadTransfer).where(
        UploadTransfer.id == transfer_id, UploadTransfer.owner_id == owner_id).with_for_update())).scalar_one_or_none()
    if row is None or row.expires_at <= utcnow() or row.status not in (STATUS_OPEN, STATUS_READY):
        raise HTTPException(404, "err.not_found")
    chunks = (await db.execute(select(UploadChunk.data).where(
        UploadChunk.transfer_id == transfer_id).order_by(UploadChunk.index))).scalars().all()
    if len(chunks) != row.chunk_count:
        raise HTTPException(409, "err.field_invalid")
    digest = hashlib.sha256()
    size = 0
    for block in chunks:
        digest.update(block)
        size += len(block)
    if size != row.size or digest.hexdigest() != row.sha256:
        raise HTTPException(422, "err.field_invalid")
    row.status = STATUS_READY
    await db.flush()
    return {"upload_id": row.id, "filename": row.filename, "size": row.size, "sha256": row.sha256}


def is_manifest(data: bytes) -> bool:
    if not data.startswith(b"{") or len(data) > 4096:
        return False
    try:
        return json.loads(data).get("magic") == MANIFEST_MAGIC
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return False


async def consume_manifest(data: bytes, owner_id: int | None) -> bytes:
    try:
        manifest = json.loads(data)
        transfer_id = manifest["upload_id"]
        if manifest.get("magic") != MANIFEST_MAGIC or not isinstance(transfer_id, str):
            raise ValueError("manifest")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(422, "err.field_invalid")
    async with get_sessionmaker()() as db:
        row = (await db.execute(select(UploadTransfer).where(
            UploadTransfer.id == transfer_id).with_for_update())).scalar_one_or_none()
        if row is None or row.status != STATUS_READY or row.expires_at <= utcnow():
            raise HTTPException(404, "err.not_found")
        if owner_id is not None and row.owner_id != owner_id:
            raise HTTPException(403, "err.forbidden")
        chunks = (await db.execute(select(UploadChunk.data).where(
            UploadChunk.transfer_id == transfer_id).order_by(UploadChunk.index))).scalars().all()
        out = b"".join(chunks)
        if len(out) != row.size or hashlib.sha256(out).hexdigest() != row.sha256:
            raise HTTPException(422, "err.field_invalid")
        await db.execute(delete(UploadChunk).where(UploadChunk.transfer_id == transfer_id))
        await db.delete(row)
        await db.commit()
    return out


async def cleanup_expired(db) -> int:
    cutoff = utcnow()
    ids = (await db.execute(select(UploadTransfer.id).where(
        UploadTransfer.expires_at < cutoff))).scalars().all()
    if ids:
        await db.execute(delete(UploadChunk).where(UploadChunk.transfer_id.in_(ids)))
        await db.execute(delete(UploadTransfer).where(UploadTransfer.id.in_(ids)))
    return len(ids)
