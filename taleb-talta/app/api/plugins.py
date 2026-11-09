"""Plugin management API — capability-gated + audited (prompt §5.4).

Only users with plugin/manage may install/enable/disable/upgrade; plugin/purge
(owner-only) is required to purge data on uninstall.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import plugins as engine
from app.core.capabilities import tt_can
from app.core.i18n import reload_strings
from app.api.deps import envelope, require_cap, client_ip, check_csrf
from app.models import Plugin

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

class ComponentIn(BaseModel):
    component: str

class UninstallIn(BaseModel):
    component: str
    purge: bool = False

@router.get("")
async def list_plugins(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "plugin/manage")
    await engine.sync_present(db)
    await db.commit()
    rows = (await db.execute(select(Plugin).order_by(Plugin.type, Plugin.name))).scalars().all()
    data = [{"component": p.component, "type": p.type, "name": p.name,
             "status": p.status, "disk_version": p.disk_version,
             "installed_version": p.installed_version,
             "needs_upgrade": p.installed_version and p.disk_version > p.installed_version}
            for p in rows]
    return envelope(True, "", data)

@router.post("/install")
async def install(body: ComponentIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    try:
        p = await engine.install(db, body.component, actor=user, ip=client_ip(request))
        await db.commit()
        reload_strings()
        return envelope(True, "ok.created", {"component": p.component, "status": p.status})
    except ValueError as e:
        await db.rollback()
        return envelope(False, "err.generic", {"error": str(e)})

@router.post("/enable")
async def enable(body: ComponentIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    p = await engine.enable(db, body.component, actor=user, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"component": p.component, "status": p.status})

@router.post("/disable")
async def disable(body: ComponentIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    p = await engine.disable(db, body.component, actor=user, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"component": p.component, "status": p.status})

@router.post("/upgrade")
async def upgrade(body: ComponentIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    p = await engine.upgrade(db, body.component, actor=user, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"component": p.component,
                                         "installed_version": p.installed_version})

@router.post("/uninstall")
async def uninstall(body: UninstallIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    if body.purge and not await tt_can(db, user, "plugin/purge"):
        raise HTTPException(status_code=403, detail="err.forbidden")
    await engine.uninstall(db, body.component, purge=body.purge, actor=user,
                           ip=client_ip(request))
    await db.commit()
    reload_strings()
    return envelope(True, "ok.deleted", {"component": body.component})


class PluginSettingsIn(BaseModel):
    values: dict[str, str | int | bool]


@router.get("/{component}/settings")
async def get_settings(component: str, request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "plugin/manage")
    try:
        return envelope(True, "", await engine.settings_for(db, component))
    except ValueError:
        raise HTTPException(404, "err.not_found")


@router.post("/{component}/settings")
async def save_settings(component: str, body: PluginSettingsIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "plugin/manage")
    await check_csrf(request, sess)
    try:
        data = await engine.save_settings(db, component, body.values, actor=user, ip=client_ip(request))
        await db.commit()
        return envelope(True, "ok.updated", data)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, str(exc))
