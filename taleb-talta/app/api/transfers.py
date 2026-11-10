"""Netlify-safe chunked uploads and permission-ticketed private downloads."""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import config
from app.api.deps import envelope, require_user, check_csrf, client_ip
from app.core import transfers, objectstore, ratelimit
from app.core.db import get_db

router = APIRouter(prefix="/api", tags=["transfers"])


class TransferIn(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0, le=25 * 1024 * 1024)
    sha256: str = Field(min_length=64, max_length=64)


@router.post("/transfers/uploads")
async def create_upload(body: TransferIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    if not await ratelimit.hit(db, f"transfer:{user.id}", limit=40, window=3600):
        await db.commit()
        return envelope(False, "err.rate_limited")
    row = await transfers.create_transfer(db, user.id, filename=body.filename,
                                          size=body.size, sha256=body.sha256)
    await db.commit()
    return envelope(True, "", {"upload_id": row.id, "chunk_size": transfers.UPLOAD_CHUNK_BYTES,
                               "chunk_count": row.chunk_count, "expires_at": row.expires_at.isoformat()})


@router.put("/transfers/uploads/{transfer_id}/chunks/{index}")
async def upload_chunk(transfer_id: str, index: int, request: Request,
                       db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    data = await request.body()
    if len(data) > transfers.UPLOAD_CHUNK_BYTES:
        raise HTTPException(413, "err.upload_size")
    await transfers.add_chunk(db, user.id, transfer_id, index, data)
    await db.commit()
    return envelope(True, "", {"index": index})


@router.post("/transfers/uploads/{transfer_id}/complete")
async def complete_upload(transfer_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    data = await transfers.complete_transfer(db, user.id, transfer_id)
    await db.commit()
    return envelope(True, "", data)


def _range_header(value: str, size: int) -> tuple[int, int] | None:
    if not value:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or size <= 0:
        raise HTTPException(416, "err.field_invalid")
    left, right = match.groups()
    if not left and not right:
        raise HTTPException(416, "err.field_invalid")
    if not left:
        length = int(right)
        if length <= 0:
            raise HTTPException(416, "err.field_invalid")
        start, end = max(0, size - length), size - 1
    else:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    if start >= size or end < start:
        raise HTTPException(416, "err.field_invalid")
    return start, end


@router.get("/files/content")
async def file_content(request: Request, ticket: str, meta: int = 0):
    payload = transfers.verify_ticket(ticket)
    obj = await objectstore.metadata(payload["k"])
    if obj is None:
        raise HTTPException(404, "err.not_found")
    name = payload.get("n") or obj.name or "file"
    mime = payload.get("m") or obj.mime
    inline = bool(payload.get("i"))
    if meta:
        return JSONResponse({"size": obj.size, "name": name, "mime": mime,
                             "chunk_size": transfers.RANGE_RESPONSE_BYTES})
    try:
        requested = _range_header(request.headers.get("range", ""), obj.size)
    except HTTPException:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{obj.size}"})
    if requested is None:
        if obj.size > transfers.DIRECT_RESPONSE_BYTES:
            # Browsers use TT.download/TT.fetchBlob for large attachments. This
            # avoids silently truncating a file at Netlify's response ceiling.
            return JSONResponse({"success": False, "message": "err.use_chunked_download",
                                 "data": {"size": obj.size}}, status_code=413)
        start, end, partial = 0, obj.size - 1, False
    else:
        start, end = requested
        end = min(end, start + transfers.RANGE_RESPONSE_BYTES - 1)
        partial = True
    safe = quote(name, safe="")
    disposition = "inline" if inline else "attachment"
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store",
               "X-Content-Type-Options": "nosniff",
               "Content-Disposition": f"{disposition}; filename*=UTF-8''{safe}",
               "Content-Length": str(end - start + 1)}
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{obj.size}"
    return StreamingResponse(objectstore.iter_range(obj.key, start, end),
                             status_code=206 if partial else 200,
                             media_type=mime if inline else "application/octet-stream",
                             headers=headers)


@router.head("/files/content")
async def file_content_head(request: Request, ticket: str):
    payload = transfers.verify_ticket(ticket)
    obj = await objectstore.metadata(payload["k"])
    if obj is None:
        raise HTTPException(404, "err.not_found")
    return Response(status_code=200, headers={"Accept-Ranges": "bytes",
                                             "Content-Length": str(obj.size),
                                             "Cache-Control": "private, no-store"})
