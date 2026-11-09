"""Custom fields, dashboard, theme and menu builder APIs (Wave 4)."""
from __future__ import annotations
import re
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import customfields, customization, moderation
from app.core.audit import audit
from app.core.capabilities import tt_can
from app.api.deps import envelope, require_user, require_cap, client_ip, check_csrf
from app.models import CustomField, CustomFieldValue, MenuItem, ThemePreset, RoleTheme, Course, User

router = APIRouter(prefix="/api", tags=["customization"])


class BlockIn(BaseModel):
    key: str
    enabled: bool
    order: int = Field(ge=0, le=100)


class BlocksIn(BaseModel):
    blocks: list[BlockIn] = Field(min_length=1, max_length=20)


class RoleBlocksIn(BlocksIn):
    role: str


class FieldIn(BaseModel):
    applies_to: str
    machine_name: str = Field(min_length=2, max_length=60)
    label: str = Field(min_length=1, max_length=120)
    field_type: str = "text"
    options: list[str] = Field(default_factory=list, max_length=30)
    required: bool = False
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=1000)


class FieldUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    options: list[str] = Field(default_factory=list, max_length=30)
    required: bool = False
    enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=1000)


class ValuesIn(BaseModel):
    values: dict


def _options(field_type, options):
    cleaned = [str(o).strip()[:120] for o in options]
    if field_type == "select" and (not cleaned or any(not o for o in cleaned) or len(set(cleaned)) != len(cleaned)):
        raise HTTPException(422, "customfield.options_invalid")
    return cleaned if field_type == "select" else []


@router.get("/custom-fields/{entity}")
async def fields(entity: str, request: Request, all: int = 0, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    if entity not in ("user", "course"):
        raise HTTPException(404, "customfield.unknown_entity")
    include_disabled = bool(all) and await tt_can(db, user, "site/settings")
    rows = await customfields.definitions(db, entity, include_disabled=include_disabled)
    return envelope(True, "", [customfields.public(f) for f in rows])


@router.post("/custom-fields")
async def create_field(body: FieldIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    if body.applies_to not in ("user", "course") or body.field_type not in ("text", "number", "select", "checkbox"):
        raise HTTPException(422, "err.field_invalid")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,59}", body.machine_name):
        raise HTTPException(422, "customfield.name_invalid")
    label = moderation.filter_text(body.label.strip(), await moderation.dictionary(db))[0]
    options = _options(body.field_type, body.options)
    duplicate = (await db.execute(select(CustomField).where(CustomField.applies_to == body.applies_to,
                 CustomField.machine_name == body.machine_name))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(409, "customfield.exists")
    row = CustomField(applies_to=body.applies_to, machine_name=body.machine_name, label=label,
                      field_type=body.field_type, options_json=options, required=body.required,
                      enabled=body.enabled, sort_order=body.sort_order, created_by=user.id)
    db.add(row)
    await db.flush()
    await audit(db, action="customization.updated", actor=user, entity_type="custom_field", entity_id=row.id,
                after=customfields.public(row), ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.created", customfields.public(row))


@router.post("/custom-fields/{field_id}")
async def update_field(field_id: int, body: FieldUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = (await db.execute(select(CustomField).where(CustomField.id == field_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    before = customfields.public(row)
    row.label = moderation.filter_text(body.label.strip(), await moderation.dictionary(db))[0]
    row.options_json = _options(row.field_type, body.options)
    row.required, row.enabled, row.sort_order = body.required, body.enabled, body.sort_order
    await audit(db, action="customization.updated", actor=user, entity_type="custom_field", entity_id=row.id,
                before=before, after=customfields.public(row), ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated", customfields.public(row))


async def _course_for_edit(db, user, course_id):
    if not await tt_can(db, user, "course/edit"):
        raise HTTPException(403, "err.forbidden")
    course = (await db.execute(select(Course).where(Course.id == course_id, Course.deleted_at.is_(None)))).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "err.course_not_found")
    if user.role not in ("owner", "admin") and course.teacher_id != user.id:
        raise HTTPException(403, "err.forbidden")
    return course


@router.get("/custom-fields/{entity}/{entity_id}/values")
async def values(entity: str, entity_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    if entity == "user":
        if entity_id != user.id and not await tt_can(db, user, "user/manage"):
            raise HTTPException(403, "err.forbidden")
    elif entity == "course":
        from app.api.courses import _get_course, _can_learn
        course = await _get_course(db, entity_id)
        if not await _can_learn(db, user, course):
            raise HTTPException(403, "err.forbidden")
    else:
        raise HTTPException(404, "customfield.unknown_entity")
    return envelope(True, "", await customfields.get_values(db, entity, entity_id))


@router.post("/custom-fields/{entity}/{entity_id}/values")
async def save_values(entity: str, entity_id: int, body: ValuesIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    if entity == "user":
        if entity_id != user.id:
            if not await tt_can(db, user, "user/manage") or user.role == "moderator":
                raise HTTPException(403, "err.forbidden")
            from app.api.admin import _guard
            target = (await db.execute(select(User).where(User.id == entity_id))).scalar_one_or_none()
            if target is None:
                raise HTTPException(404, "err.user_not_found")
            _guard(user, target, changing_privilege=True)
        cleaned = await customfields.validate_values(db, entity, body.values, user=user, count_strike=entity_id == user.id)
    elif entity == "course":
        await _course_for_edit(db, user, entity_id)
        cleaned = await customfields.validate_values(db, entity, body.values)
    else:
        raise HTTPException(404, "customfield.unknown_entity")
    before = await customfields.get_values(db, entity, entity_id)
    await customfields.save_values(db, entity, entity_id, cleaned)
    await audit(db, action="customization.updated", actor=user, entity_type=f"{entity}_fields", entity_id=entity_id,
                before=before, after=cleaned, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", cleaned)


@router.get("/dashboard")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    return envelope(True, "", await customization.dashboard(db, user))


@router.post("/dashboard/preferences")
async def preferences(body: BlocksIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    await customization.save_preferences(db, user, [b.model_dump() for b in body.blocks])
    await db.commit()
    return envelope(True, "ok.updated")


@router.get("/admin/dashboard/defaults/{role}")
async def defaults(role: str, request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "site/settings")
    if role not in customization.ROLES:
        raise HTTPException(404, "err.not_found")
    from app.models import DashboardBlock
    rows = (await db.execute(select(DashboardBlock).where(DashboardBlock.role == role)
                .order_by(DashboardBlock.sort_order))).scalars().all()
    return envelope(True, "", [{"key": r.block_key, "enabled": r.enabled, "order": r.sort_order} for r in rows])


@router.post("/admin/dashboard/defaults")
async def save_defaults(body: RoleBlocksIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    await customization.save_defaults(db, body.role, [b.model_dump() for b in body.blocks])
    await audit(db, action="customization.updated", actor=user, entity_type="dashboard", entity_id=body.role,
                after={"blocks": [b.model_dump() for b in body.blocks]}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_theme: str = "light"
    primary: str
    secondary: str
    accent: str
    radius: int = Field(default=16, ge=8, le=24)
    density: str = "comfortable"


class ThemeIn(BaseModel):
    theme_key: str


class RoleThemeIn(ThemeIn):
    role: str


@router.get("/themes")
async def themes(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(RoleTheme))).scalars().all()
    return envelope(True, "", {"presets": [customization.preset_public(p) for p in await customization.presets(db)],
                               "active": await customization.active_theme(db, user),
                               "role_overrides": {r.role: r.theme_key for r in rows}})


@router.post("/admin/themes")
async def create_preset(body: PresetIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = await customization.create_preset(db, body.model_dump(), user)
    await audit(db, action="customization.updated", actor=user, entity_type="theme", entity_id=row.id,
                after=customization.preset_public(row), ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.created", customization.preset_public(row))


@router.post("/admin/themes/activate")
async def activate(body: ThemeIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    if not await customization.valid_theme(db, body.theme_key):
        raise HTTPException(422, "theme.unknown")
    await customization.set_setting(db, "site.theme", body.theme_key)
    await audit(db, action="customization.updated", actor=user, entity_type="theme", entity_id=body.theme_key,
                after={"active": body.theme_key}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")


@router.post("/admin/themes/role")
async def role_theme(body: RoleThemeIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    if body.role not in customization.ROLES or not await customization.valid_theme(db, body.theme_key):
        raise HTTPException(422, "theme.unknown")
    row = (await db.execute(select(RoleTheme).where(RoleTheme.role == body.role))).scalar_one_or_none()
    if row is None:
        db.add(RoleTheme(role=body.role, theme_key=body.theme_key))
    else:
        row.theme_key = body.theme_key
    await audit(db, action="customization.updated", actor=user, entity_type="role_theme", entity_id=body.role,
                after={"theme": body.theme_key}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated")


@router.delete("/admin/themes/{preset_id}")
async def delete_preset(preset_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    key = f"preset-{preset_id}"
    active = await customization._setting(db, "site.theme")
    assigned = (await db.execute(select(RoleTheme).where(RoleTheme.theme_key == key))).first()
    if active == key or assigned:
        raise HTTPException(409, "theme.in_use")
    row = (await db.execute(select(ThemePreset).where(ThemePreset.id == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    await db.delete(row)
    await audit(db, action="customization.updated", actor=user, entity_type="theme", entity_id=key,
                after={"deleted": True}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.deleted")


class MenuIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=255)
    icon: str = "book"
    role: str = ""
    order: int = Field(default=0, ge=0, le=1000)
    enabled: bool = True


@router.get("/admin/menus")
async def menus(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "site/settings")
    rows = (await db.execute(select(MenuItem).order_by(MenuItem.sort_order, MenuItem.id))).scalars().all()
    return envelope(True, "", [customization.menu_public(m) for m in rows])


@router.post("/admin/menus")
async def create_menu(body: MenuIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = await customization.save_menu(db, body.model_dump())
    await audit(db, action="customization.updated", actor=user, entity_type="menu", entity_id=row.id,
                after=customization.menu_public(row), ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.created", customization.menu_public(row))


@router.post("/admin/menus/{menu_id}")
async def update_menu(menu_id: int, body: MenuIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = await customization.save_menu(db, body.model_dump(), menu_id)
    await audit(db, action="customization.updated", actor=user, entity_type="menu", entity_id=row.id,
                after=customization.menu_public(row), ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated", customization.menu_public(row))


@router.delete("/admin/menus/{menu_id}")
async def delete_menu(menu_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "site/settings")
    await check_csrf(request, sess)
    row = (await db.execute(select(MenuItem).where(MenuItem.id == menu_id))).scalar_one_or_none()
    if row is None or row.plugin_id is not None:
        raise HTTPException(404, "menu.not_editable")
    await db.delete(row)
    await audit(db, action="customization.updated", actor=user, entity_type="menu", entity_id=menu_id,
                after={"deleted": True}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.deleted")
