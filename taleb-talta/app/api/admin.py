"""Site administration API: typed settings, branding, users and divisions."""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import settings as site_settings, customfields, community, files, moderation
from app.core import session as sessmgr
from app.core.audit import audit
from app.core.auth import normalize_phone, valid_phone
from app.core.capabilities import tt_can
from app.api.deps import envelope, require_cap, client_ip, check_csrf
from app.models import User, Division, SiteSetting, Channel, ChannelMember, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"])
ROLES = ("owner", "admin", "moderator", "teacher", "student", "parent")


class SettingsIn(BaseModel):
    values: dict[str, str | int | bool] = Field(max_length=30)


@router.get("/settings")
async def get_settings(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    values = await site_settings.public_values(db)
    specs = {k: {"group": s.group, "type": s.kind, "default": s.default,
                 "min": s.minimum, "max": s.maximum}
             for k, s in site_settings.SPECS.items() if s.capability == "site/settings"}
    logo = await site_settings.raw(db, "site.logo_path")
    return envelope(True, "", {"values": values, "specs": specs, "has_logo": bool(logo)})


@router.post("/settings")
async def save_settings(body: SettingsIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    for key in body.values:
        if key not in site_settings.SPECS or site_settings.SPECS[key].capability != "site/settings":
            raise HTTPException(403, "admin.setting_forbidden")
    try:
        cleaned = {k: site_settings.validate(k, v) for k, v in body.values.items()}
        if cleaned.get("site.name"):
            cleaned["site.name"] = moderation.filter_text(cleaned["site.name"], await moderation.dictionary(db))[0]
        values = await site_settings.save(db, cleaned, actor=user, ip=client_ip(request))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc))
    return envelope(True, "ok.updated", values)


@router.get("/security")
async def get_security(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "site/security")
    values = await site_settings.security_policy(db)
    specs = {k: {"type": s.kind, "default": s.default, "min": s.minimum, "max": s.maximum}
             for k, s in site_settings.SPECS.items() if s.capability == "site/security"}
    return envelope(True, "", {"values": values, "specs": specs})


@router.post("/security")
async def save_security(body: SettingsIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/security")
    await check_csrf(request, sess)
    for key in body.values:
        if key not in site_settings.SPECS or site_settings.SPECS[key].capability != "site/security":
            raise HTTPException(403, "admin.setting_forbidden")
    try:
        values = await site_settings.save(db, body.values, actor=user, ip=client_ip(request))
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc))
    return envelope(True, "ok.updated", values)


@router.post("/logo")
async def upload_logo(request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    data = await file.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(413, "err.upload_size")
    try:
        saved = files.save("branding", file.filename or "logo.png", data)
    except files.FileError as exc:
        raise HTTPException(422, exc.key)
    if not saved["mime"].startswith("image/"):
        files.delete(saved["key"])
        raise HTTPException(422, "err.upload_type")
    old = await site_settings.raw(db, "site.logo_path")
    row = (await db.execute(select(SiteSetting).where(SiteSetting.key == "site.logo_path"))).scalar_one_or_none()
    if row is None:
        db.add(SiteSetting(key="site.logo_path", value=saved["key"]))
    else:
        row.value = saved["key"]
    await audit(db, action="settings.updated", actor=user, entity_type="site_settings",
                entity_id="site.logo_path", before={"configured": bool(old)}, after={"configured": True},
                ip=client_ip(request), severity="notice")
    await db.commit()
    if old:
        files.delete(old)
    return envelope(True, "ok.updated", {"url": "/branding/logo"})


@router.get("/users")
async def users(request: Request, q: str = "", role: str = "", status: str = "",
                division_id: int = 0, page: int = 1, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/manage")
    page = max(1, min(page, 10000))
    query = select(User)
    if q:
        term = f"%{q.strip()[:100]}%"
        query = query.where(or_(User.name.ilike(term), User.phone.ilike(term)))
    if role:
        if role not in ROLES:
            raise HTTPException(422, "err.field_invalid")
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    if division_id:
        query = query.where(User.division_id == division_id)
    if actor.role == "moderator":
        query = query.where(User.role.in_(("student", "parent")))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(User.id).offset((page - 1) * 30).limit(30))).scalars().all()
    data = [{"id": u.id, "name": u.name, "phone": u.phone, "guardian_phone": u.guardian_phone,
             "role": u.role, "status": u.status, "division_id": u.division_id,
             "last_login": u.last_login.isoformat() if u.last_login else "",
             "created_at": u.created_at.isoformat()} for u in rows]
    return envelope(True, "", {"rows": data, "total": total, "page": page, "pages": max(1, (total + 29) // 30)})


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    phone: str | None = None
    guardian_phone: str | None = None
    role: str | None = None
    status: str | None = None
    division_id: int | None = None
    custom_fields: dict | None = None


def _guard(actor, target, *, changing_privilege=False):
    if actor.role == "owner":
        return
    if actor.role == "admin" and target.role not in ("owner", "admin"):
        return
    if actor.role == "moderator" and target.role in ("student", "parent") and not changing_privilege:
        return
    raise HTTPException(403, "admin.user_forbidden")


@router.post("/users/{user_id}")
async def update_user(user_id: int, body: UserUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/manage")
    await check_csrf(request, sess)
    if actor.role == "moderator":
        raise HTTPException(403, "admin.user_forbidden")
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "err.user_not_found")
    _guard(actor, target, changing_privilege=True)
    changes = body.model_dump(exclude_unset=True)
    if target.id == actor.id and any(k in changes for k in ("role", "status", "phone")):
        raise HTTPException(400, "admin.self_change")
    if "role" in changes:
        if changes["role"] not in ROLES or (actor.role != "owner" and changes["role"] in ("owner", "admin")):
            raise HTTPException(403, "admin.role_forbidden")
        if target.role == "owner" and changes["role"] != "owner":
            owners = (await db.execute(select(func.count(User.id)).where(User.role == "owner"))).scalar_one()
            if owners <= 1:
                raise HTTPException(409, "admin.last_owner")
    if "status" in changes and changes["status"] not in ("active", "suspended", "banned", "pending"):
        raise HTTPException(422, "err.field_invalid")
    for key in ("phone", "guardian_phone"):
        if key in changes and changes[key] is not None:
            changes[key] = normalize_phone(changes[key])
            if not valid_phone(changes[key]):
                raise HTTPException(422, "err.invalid_phone")
    if "phone" in changes:
        duplicate = (await db.execute(select(User.id).where(User.phone == changes["phone"], User.id != target.id))).first()
        if duplicate:
            raise HTTPException(409, "err.phone_exists")
    if changes.get("division_id"):
        if not (await db.execute(select(Division).where(Division.id == changes["division_id"]))).scalar_one_or_none():
            raise HTTPException(404, "admin.division_not_found")
    before = {k: getattr(target, k) for k in ("name", "phone", "guardian_phone", "role", "status", "division_id")}
    custom = None
    if "custom_fields" in changes:
        custom = await customfields.validate_values(db, "user", changes.pop("custom_fields") or {})
    if "name" in changes:
        changes["name"] = moderation.filter_text(changes["name"] or "", await moderation.dictionary(db))[0].strip()
        if not changes["name"]:
            raise HTTPException(422, "err.required")
    for key, value in changes.items():
        setattr(target, key, value)
    if target.status == "banned" and "banned_until" not in changes:
        target.banned_until = None
    if "division_id" in changes:
        old_channel = (await db.execute(select(Channel).where(Channel.kind == "division",
                       Channel.division_id == before["division_id"]))).scalar_one_or_none()
        if old_channel:
            member = (await db.execute(select(ChannelMember).where(ChannelMember.channel_id == old_channel.id,
                      ChannelMember.user_id == target.id))).scalar_one_or_none()
            if member:
                await db.delete(member)
        await community.add_division_member(db, target)
    if custom is not None:
        await customfields.save_values(db, "user", target.id, custom)
    if any(k in changes for k in ("role", "status", "phone")):
        await sessmgr.revoke_all_for_user(db, target.id)
    await audit(db, action="admin.user_updated", actor=actor, entity_type="user", entity_id=target.id,
                before=before, after={k: getattr(target, k) for k in before}, ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "ok.updated")


class StatusIn(BaseModel):
    status: str


@router.post("/users/{user_id}/status")
async def set_status(user_id: int, body: StatusIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/manage")
    await check_csrf(request, sess)
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "err.user_not_found")
    _guard(actor, target)
    if target.id == actor.id or body.status not in ("active", "suspended", "banned"):
        raise HTTPException(422, "admin.status_invalid")
    if actor.role == "moderator" and body.status == "banned":
        raise HTTPException(403, "admin.user_forbidden")
    before = target.status
    target.status = body.status
    target.banned_until = None
    await sessmgr.revoke_all_for_user(db, target.id)
    await audit(db, action="admin.user_updated", actor=actor, entity_type="user", entity_id=target.id,
                before={"status": before}, after={"status": body.status}, ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "ok.updated")


class DivisionIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/divisions")
async def create_division(body: DivisionIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    name = moderation.filter_text(body.name.strip(), await moderation.dictionary(db))[0]
    if (await db.execute(select(Division).where(Division.name == name))).scalar_one_or_none():
        raise HTTPException(409, "admin.division_exists")
    row = Division(name=name)
    db.add(row)
    await db.flush()
    db.add(Channel(kind="division", title=name, division_id=row.id, created_by=actor.id))
    await audit(db, action="admin.division_created", actor=actor, entity_type="division", entity_id=row.id,
                after={"name": name}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.created", {"id": row.id, "name": row.name})


@router.post("/divisions/{division_id}")
async def rename_division(division_id: int, body: DivisionIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = (await db.execute(select(Division).where(Division.id == division_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "admin.division_not_found")
    name = moderation.filter_text(body.name.strip(), await moderation.dictionary(db))[0]
    duplicate = (await db.execute(select(Division.id).where(Division.name == name, Division.id != row.id))).first()
    if duplicate:
        raise HTTPException(409, "admin.division_exists")
    before = row.name
    row.name = name
    channel = (await db.execute(select(Channel).where(Channel.kind == "division", Channel.division_id == row.id))).scalar_one_or_none()
    if channel:
        channel.title = name
    await audit(db, action="admin.division_updated", actor=actor, entity_type="division", entity_id=row.id,
                before={"name": before}, after={"name": name}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")
