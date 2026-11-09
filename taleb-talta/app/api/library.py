"""Shared library + moderation + private space (Wave 1, spec §6.11).

Submit -> pending -> moderator approve/reject (with reason). Approved items are
listed in the shared library; each student can copy them into a private,
access-controlled space. Files are served only through permission-checked
endpoints (never a public URL).
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import files, ratelimit, moderation
from app.core.audit import audit
from app.api.deps import (envelope, require_user, require_cap, client_ip,
                          user_agent, check_csrf)
from app.models import LibraryItem, UserLibrary, User, utcnow

router = APIRouter(prefix="/api/library", tags=["library"])


async def _get_item(db, item_id) -> LibraryItem:
    it = (await db.execute(select(LibraryItem).where(
        LibraryItem.id == item_id))).scalar_one_or_none()
    if it is None:
        raise HTTPException(status_code=404, detail="err.library_not_found")
    return it


def _serialize(it: LibraryItem, uploader_name: str = "") -> dict:
    return {"id": it.id, "title": it.title, "description": it.description,
            "category": it.category, "status": it.status, "file_name": it.file_name,
            "file_size": it.file_size, "mime": it.mime,
            "download_count": it.download_count, "review_reason": it.review_reason,
            "uploader_name": uploader_name,
            "created_at": it.created_at.isoformat() if it.created_at else ""}


@router.get("")
async def shared_library(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(LibraryItem).where(
        LibraryItem.status == "approved").order_by(
        LibraryItem.created_at.desc()))).scalars().all()
    names = {u.id: u.name for u in (await db.execute(select(User))).scalars().all()}
    saved = {r.library_item_id for r in (await db.execute(select(UserLibrary).where(
        UserLibrary.user_id == user.id))).scalars().all()}
    out = []
    for it in rows:
        d = _serialize(it, names.get(it.uploader_id, ""))
        d["saved"] = it.id in saved
        out.append(d)
    return envelope(True, "", out)


@router.post("/submit")
async def submit(request: Request,
                 title: str = Form(...), description: str = Form(""),
                 category: str = Form(""), upload: UploadFile = File(...),
                 db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "library/upload")
    await check_csrf(request, sess)
    if not title.strip():
        return envelope(False, "err.required")
    if not await ratelimit.hit(db, f"libup:{user.id}", limit=10, window=3600):
        await db.commit()
        return envelope(False, "err.rate_limited")
    screened = await moderation.screen(db, user, {"title": title, "description": description, "category": category},
                                       source="library.submit", ip=client_ip(request))
    try:
        data = await files.read_upload(upload)
        saved = files.save("library", upload.filename or "file", data)
    except files.FileError as e:
        return envelope(False, e.key)
    it = LibraryItem(uploader_id=user.id, title=screened.values["title"].strip()[:200],
                     description=screened.values["description"], category=screened.values["category"].strip()[:120],
                     division_id=user.division_id,
                     file_path=saved["key"], file_name=saved["file_name"],
                     file_size=saved["file_size"], mime=saved["mime"], status="pending")
    db.add(it)
    await db.flush()
    await audit(db, action="library.submitted", actor=user, entity_type="library_item",
                entity_id=it.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "lib.submitted", {"id": it.id})


@router.get("/pending")
async def pending(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "library/moderate")
    rows = (await db.execute(select(LibraryItem).where(
        LibraryItem.status == "pending").order_by(LibraryItem.created_at))).scalars().all()
    names = {u.id: u.name for u in (await db.execute(select(User))).scalars().all()}
    return envelope(True, "", [_serialize(it, names.get(it.uploader_id, "")) for it in rows])


@router.post("/{item_id}/approve")
async def approve(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "library/moderate")
    await check_csrf(request, sess)
    it = await _get_item(db, item_id)
    it.status = "approved"
    it.reviewed_by = user.id
    it.reviewed_at = utcnow()
    it.review_reason = ""
    await audit(db, action="library.approved", actor=user, entity_type="library_item",
                entity_id=it.id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "lib.approved_ok")


class RejectIn(BaseModel):
    reason: str = ""

@router.post("/{item_id}/reject")
async def reject(item_id: int, body: RejectIn, request: Request,
                 db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "library/moderate")
    await check_csrf(request, sess)
    if not body.reason.strip():
        return envelope(False, "err.reject_reason_required")
    it = await _get_item(db, item_id)
    it.status = "rejected"
    it.reviewed_by = user.id
    it.reviewed_at = utcnow()
    it.review_reason = body.reason.strip()
    await audit(db, action="library.rejected", actor=user, entity_type="library_item",
                entity_id=it.id, ip=client_ip(request), severity="notice",
                after={"reason": it.review_reason})
    await db.commit()
    return envelope(True, "lib.rejected_ok")


@router.get("/mine")
async def my_space(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(UserLibrary).where(
        UserLibrary.user_id == user.id).order_by(UserLibrary.saved_at.desc()))).scalars().all()
    out = []
    for r in rows:
        it = (await db.execute(select(LibraryItem).where(
            LibraryItem.id == r.library_item_id))).scalar_one_or_none()
        if it is None:
            continue
        d = _serialize(it)
        d["private_id"] = r.id
        out.append(d)
    return envelope(True, "", out)


@router.post("/{item_id}/save")
async def save_to_space(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    it = await _get_item(db, item_id)
    if it.status != "approved":
        return envelope(False, "err.forbidden")
    exists = (await db.execute(select(UserLibrary).where(
        UserLibrary.user_id == user.id,
        UserLibrary.library_item_id == it.id))).scalar_one_or_none()
    if exists:
        return envelope(False, "err.already_saved")
    db.add(UserLibrary(user_id=user.id, library_item_id=it.id))
    await db.flush()
    await db.commit()
    return envelope(True, "lib.saved_to_space")


def _serve(it: LibraryItem, increment: bool = True):
    path = files.resolve(it.file_path)
    return FileResponse(path, media_type=it.mime or "application/octet-stream",
                        filename=it.file_name)


@router.get("/{item_id}/download")
async def download(item_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    it = await _get_item(db, item_id)
    from app.core.capabilities import tt_can
    allowed = (it.status == "approved" or it.uploader_id == user.id
               or await tt_can(db, user, "library/moderate"))
    if not allowed:
        raise HTTPException(status_code=403, detail="err.forbidden")
    if it.status == "approved":
        it.download_count += 1
        await db.commit()
    return _serve(it)


@router.get("/private/{private_id}/download")
async def download_private(private_id: int, request: Request,
                           db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    r = (await db.execute(select(UserLibrary).where(
        UserLibrary.id == private_id))).scalar_one_or_none()
    if r is None or r.user_id != user.id:
        raise HTTPException(status_code=403, detail="err.forbidden")
    it = await _get_item(db, r.library_item_id)
    return _serve(it)
