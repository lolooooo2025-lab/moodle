"""Durable private object storage in PostgreSQL/Neon.

Netlify's filesystem is ephemeral.  The application keeps its existing opaque
storage keys and permission checks, but the authoritative bytes live in Neon.
Files are split into bounded rows so neither uploads nor downloads depend on
one oversized SQL parameter or one oversized serverless response.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select, delete, func

from app import config
from app.core.db import get_sessionmaker
from app.models import StoredObject, StoredChunk, utcnow

CHUNK_BYTES = 1024 * 1024


def cache_path(key: str) -> Path:
    base = config.STORAGE_DIR.resolve()
    path = (base / key).resolve()
    if base not in path.parents:
        raise ValueError("invalid storage key")
    return path


async def put_bytes(key: str, data: bytes, *, mime: str, name: str) -> StoredObject:
    digest = hashlib.sha256(data).hexdigest()
    async with get_sessionmaker()() as db:
        await db.execute(delete(StoredChunk).where(StoredChunk.object_key == key))
        await db.execute(delete(StoredObject).where(StoredObject.key == key))
        obj = StoredObject(key=key, size=len(data), sha256=digest, mime=mime,
                           name=name, created_at=utcnow())
        db.add(obj)
        await db.flush()  # the parent row must exist before FK-checked chunks
        for index, start in enumerate(range(0, len(data), CHUNK_BYTES)):
            db.add(StoredChunk(object_key=key, index=index, data=data[start:start + CHUNK_BYTES]))
        await db.commit()
    return obj


async def put_file(key: str, path: Path, *, mime: str, name: str) -> StoredObject:
    size = path.stat().st_size
    digest = hashlib.sha256()
    async with get_sessionmaker()() as db:
        await db.execute(delete(StoredChunk).where(StoredChunk.object_key == key))
        await db.execute(delete(StoredObject).where(StoredObject.key == key))
        obj = StoredObject(key=key, size=size, sha256="", mime=mime, name=name,
                           created_at=utcnow())
        db.add(obj)
        await db.flush()
        with path.open("rb") as handle:
            index = 0
            while True:
                block = handle.read(CHUNK_BYTES)
                if not block:
                    break
                digest.update(block)
                db.add(StoredChunk(object_key=key, index=index, data=block))
                index += 1
                if index % 16 == 0:
                    await db.flush()
        obj.sha256 = digest.hexdigest()
        await db.commit()
    return obj


async def metadata(key: str) -> StoredObject | None:
    async with get_sessionmaker()() as db:
        return (await db.execute(select(StoredObject).where(StoredObject.key == key))).scalar_one_or_none()


async def read_bytes(key: str) -> bytes:
    obj = await metadata(key)
    if obj is None:
        raise FileNotFoundError(key)
    out = bytearray()
    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(StoredChunk.data).where(
            StoredChunk.object_key == key).order_by(StoredChunk.index))).scalars().all()
        for block in rows:
            out.extend(block)
    if len(out) != obj.size or hashlib.sha256(out).hexdigest() != obj.sha256:
        raise RuntimeError("stored_object_corrupt")
    return bytes(out)


async def hydrate(key: str) -> Path:
    """Materialise a private object in /tmp for APIs that expect a real file."""
    path = cache_path(key)
    obj = await metadata(key)
    if obj is None:
        raise FileNotFoundError(key)
    if path.is_file() and path.stat().st_size == obj.size:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".partial")
    digest = hashlib.sha256()
    size = 0
    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(StoredChunk.data).where(
            StoredChunk.object_key == key).order_by(StoredChunk.index))).scalars().all()
        with tmp.open("wb") as handle:
            for block in rows:
                digest.update(block)
                size += len(block)
                handle.write(block)
    if size != obj.size or digest.hexdigest() != obj.sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("stored_object_corrupt")
    tmp.replace(path)
    return path


async def write_to_file(key: str, dest: Path):
    obj = await metadata(key)
    if obj is None:
        raise FileNotFoundError(key)
    digest = hashlib.sha256()
    size = 0
    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(StoredChunk.data).where(
            StoredChunk.object_key == key).order_by(StoredChunk.index))).scalars().all()
        with dest.open("wb") as handle:
            for block in rows:
                digest.update(block)
                size += len(block)
                handle.write(block)
    if size != obj.size or digest.hexdigest() != obj.sha256:
        raise RuntimeError("stored_object_corrupt")


async def remove(key: str):
    async with get_sessionmaker()() as db:
        await db.execute(delete(StoredChunk).where(StoredChunk.object_key == key))
        await db.execute(delete(StoredObject).where(StoredObject.key == key))
        await db.commit()
    try:
        cache_path(key).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


async def iter_range(key: str, start: int, end: int):
    """Yield an inclusive byte range without loading the whole object."""
    first, last = start // CHUNK_BYTES, end // CHUNK_BYTES
    async with get_sessionmaker()() as db:
        rows = (await db.execute(select(StoredChunk.index, StoredChunk.data).where(
            StoredChunk.object_key == key, StoredChunk.index >= first,
            StoredChunk.index <= last).order_by(StoredChunk.index))).all()
    expected = first
    for index, block in rows:
        if index != expected:
            raise RuntimeError("stored_object_corrupt")
        lo = max(start, index * CHUNK_BYTES) - index * CHUNK_BYTES
        hi = min(end + 1, (index + 1) * CHUNK_BYTES) - index * CHUNK_BYTES
        yield block[lo:hi]
        expected += 1
    if expected != last + 1:
        raise RuntimeError("stored_object_corrupt")


async def total_size() -> int:
    async with get_sessionmaker()() as db:
        return int((await db.execute(select(func.coalesce(func.sum(StoredObject.size), 0)))).scalar_one())
