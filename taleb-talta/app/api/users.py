"""Users + divisions API. Divisions are public (registration form); profile
editing is self-service for the non-core fields (spec §11); ban/force-logout are
capability-gated admin actions.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import session as sessmgr
from app.core.audit import audit
from app.core import moderation, customfields
from app.api.deps import (envelope, require_user, require_cap, client_ip,
                          user_agent, check_csrf)
from app.models import User, Division, utcnow
from app.core.capabilities import tt_can
from fastapi import HTTPException
from datetime import timedelta

router = APIRouter(prefix="/api/users", tags=["users"])

class ProfileIn(BaseModel):
    name: str = ""
    title: str = ""
    badge: str = ""
    custom_fields: dict | None = None

class BanIn(BaseModel):
    user_id: int
    days: int = 30

class UserIdIn(BaseModel):
    user_id: int

@router.get("/divisions")
async def divisions(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Division).order_by(Division.name))).scalars().all()
    return envelope(True, "", [{"id": d.id, "name": d.name} for d in rows])

@router.get("")
async def list_users(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "user/manage")
    rows = (await db.execute(select(User).order_by(User.id).limit(200))).scalars().all()
    return envelope(True, "", [{"id": u.id, "name": u.name, "phone": u.phone,
                                "role": u.role, "status": u.status,
                                "division_id": u.division_id} for u in rows])

@router.post("/profile")
async def update_profile(body: ProfileIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    screened = await moderation.screen(db, user, {"name": body.name, "title": body.title, "badge": body.badge},
                                       source="profile", ip=client_ip(request))
    body.name, body.title, body.badge = screened.values["name"], screened.values["title"], screened.values["badge"]
    custom = await customfields.validate_values(db, "user", body.custom_fields or {}, user=user, count_strike=True)
    before = {"name": user.name, "title": user.title, "badge": user.badge}
    # Only non-core fields are editable here (spec §11). Phone/guardian/division
    # change only via support.
    if body.name.strip():
        user.name = body.name.strip()[:160]
    user.title = body.title[:120]
    user.badge = body.badge[:120]
    await customfields.save_values(db, "user", user.id, custom)
    await db.commit()  # moderation strikes are durable even if the audit write fails
    await audit(db, action="user.profile_updated", actor=user, entity_type="user",
                entity_id=user.id, before=before,
                after={"name": user.name, "title": user.title, "badge": user.badge},
                ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.profile_updated")

@router.post("/ban")
async def ban(body: BanIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/ban")
    await check_csrf(request, sess)
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target is None:
        return envelope(False, "err.user_not_found")
    from app.api.admin import _guard
    _guard(actor, target)
    if target.id == actor.id or not 1 <= body.days <= 365:
        raise HTTPException(422, "admin.status_invalid")
    target.status = "banned"
    target.banned_until = utcnow() + timedelta(days=body.days)
    await sessmgr.revoke_all_for_user(db, target.id)
    await audit(db, action="user.banned", actor=actor, entity_type="user",
                entity_id=target.id, after={"days": body.days},
                ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "ok.updated")

@router.post("/force_logout")
async def force_logout(body: UserIdIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/force_logout")
    await check_csrf(request, sess)
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "err.user_not_found")
    from app.api.admin import _guard
    _guard(actor, target)
    await sessmgr.revoke_all_for_user(db, body.user_id)
    await audit(db, action="user.force_logout", actor=actor, entity_type="user",
                entity_id=body.user_id, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")


@router.post("/unban")
async def unban(body: UserIdIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, actor = await require_cap(request, db, "user/ban")
    await check_csrf(request, sess)
    target = (await db.execute(select(User).where(User.id == body.user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "err.user_not_found")
    from app.api.admin import _guard
    _guard(actor, target)
    before = {"status": target.status, "banned_until": target.banned_until.isoformat() if target.banned_until else None}
    target.status, target.banned_until = "active", None
    await sessmgr.revoke_all_for_user(db, target.id)
    await audit(db, action="user.unbanned", actor=actor, entity_type="user", entity_id=target.id,
                before=before, after={"status": "active"}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")

@router.get("/me/custom-fields")
async def my_custom_fields(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    return envelope(True, "", {"fields": [customfields.public(f) for f in await customfields.definitions(db, "user")],
                               "values": await customfields.get_values(db, "user", user.id)})
