"""Persisted dashboard/menu/theme builders. User HTML/CSS/JS is never accepted."""
from __future__ import annotations
import re
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import select, delete
from app import config
from app.models import (DashboardBlock, DashboardPreference, ThemePreset, RoleTheme,
                        MenuItem, SiteSetting, User)

ROLES = ("owner", "admin", "moderator", "teacher", "student", "parent")
ICONS = ("book", "library", "exam", "chat", "bell", "user", "users", "home", "settings", "shield", "download")


async def seed_defaults(db):
    for role in ROLES:
        for order, key in enumerate(config.DASHBOARD_BLOCKS):
            exists = (await db.execute(select(DashboardBlock).where(
                DashboardBlock.role == role, DashboardBlock.block_key == key))).scalar_one_or_none()
            if exists is None:
                db.add(DashboardBlock(role=role, block_key=key, sort_order=order,
                                      enabled=key != "digest"))
    await db.flush()


async def dashboard(db, user: User) -> list[dict]:
    defaults = (await db.execute(select(DashboardBlock).where(DashboardBlock.role == user.role)
                .order_by(DashboardBlock.sort_order, DashboardBlock.id))).scalars().all()
    prefs = {p.block_key: p for p in (await db.execute(select(DashboardPreference).where(
        DashboardPreference.user_id == user.id))).scalars()}
    result = []
    for b in defaults:
        p = prefs.get(b.block_key)
        result.append({"key": b.block_key, "enabled": p.enabled if p else b.enabled,
                       "order": p.sort_order if p else b.sort_order})
    return sorted(result, key=lambda b: (b["order"], b["key"]))


async def save_preferences(db, user: User, blocks: list[dict]):
    if len(blocks) != len(config.DASHBOARD_BLOCKS) or {b["key"] for b in blocks} != set(config.DASHBOARD_BLOCKS):
        raise HTTPException(422, "customization.blocks_invalid")
    if len({b["order"] for b in blocks}) != len(blocks):
        raise HTTPException(422, "customization.order_invalid")
    await db.execute(delete(DashboardPreference).where(DashboardPreference.user_id == user.id))
    for b in blocks:
        db.add(DashboardPreference(user_id=user.id, block_key=b["key"],
                                   enabled=b["enabled"], sort_order=b["order"]))
    await db.flush()


async def save_defaults(db, role: str, blocks: list[dict]):
    if role not in ROLES or len(blocks) != len(config.DASHBOARD_BLOCKS) or {b["key"] for b in blocks} != set(config.DASHBOARD_BLOCKS):
        raise HTTPException(422, "customization.blocks_invalid")
    if len({b["order"] for b in blocks}) != len(blocks):
        raise HTTPException(422, "customization.order_invalid")
    for b in blocks:
        row = (await db.execute(select(DashboardBlock).where(
            DashboardBlock.role == role, DashboardBlock.block_key == b["key"]))).scalar_one()
        row.enabled, row.sort_order = b["enabled"], b["order"]
    await db.flush()


def preset_public(p: ThemePreset) -> dict:
    return {"id": p.id, "key": f"preset-{p.id}", "name": p.name, "base_theme": p.base_theme,
            "primary": p.primary_color, "secondary": p.secondary_color, "accent": p.accent_color,
            "radius": p.radius, "density": p.density}


async def presets(db):
    return (await db.execute(select(ThemePreset).order_by(ThemePreset.id))).scalars().all()


async def theme_keys(db) -> dict:
    return {f"preset-{p.id}": preset_public(p) for p in await presets(db)}


async def active_theme(db, user: User | None = None) -> str:
    if user:
        row = (await db.execute(select(RoleTheme).where(RoleTheme.role == user.role))).scalar_one_or_none()
        if row:
            return row.theme_key
    return await _setting(db, "site.theme", config.DEFAULT_THEME)


async def _setting(db, key, default=""):
    row = (await db.execute(select(SiteSetting).where(SiteSetting.key == key))).scalar_one_or_none()
    return row.value if row else default


async def set_setting(db, key, value):
    row = (await db.execute(select(SiteSetting).where(SiteSetting.key == key))).scalar_one_or_none()
    if row is None:
        db.add(SiteSetting(key=key, value=value))
    else:
        row.value = value
    await db.flush()


async def valid_theme(db, key: str) -> bool:
    return key in config.THEMES or key in await theme_keys(db)


async def create_preset(db, data: dict, actor: User) -> ThemePreset:
    name = data["name"].strip()
    if not name or len(name) > 120:
        raise HTTPException(422, "err.required")
    colors = [data["primary"], data["secondary"], data["accent"]]
    if (data["primary"] not in ("#0848A4", "#113B77", "#0A1831")
            or any(c not in config.BRAND_PALETTE for c in colors) or len(set(colors)) != 3):
        raise HTTPException(422, "theme.palette_invalid")
    if data["base_theme"] not in config.THEMES or data["density"] not in ("comfortable", "compact") or not 8 <= data["radius"] <= 24:
        raise HTTPException(422, "err.field_invalid")
    if (await db.execute(select(ThemePreset).where(ThemePreset.name == name))).scalar_one_or_none():
        raise HTTPException(409, "theme.name_exists")
    row = ThemePreset(name=name, base_theme=data["base_theme"], primary_color=data["primary"],
                      secondary_color=data["secondary"], accent_color=data["accent"],
                      radius=data["radius"], density=data["density"], created_by=actor.id)
    db.add(row)
    await db.flush()
    return row


async def theme_css(db) -> str:
    # All interpolated values come from constrained columns / a fixed palette.
    rules = []
    for p in await presets(db):
        rules.append(f':root[data-theme="preset-{p.id}"]{{--primary:{p.primary_color};'
                     f'--primary-strong:{p.primary_color};--secondary:{p.secondary_color};'
                     f'--accent:{p.accent_color};--radius:{p.radius}px}}')
    return "\n".join(rules) + "\n"


def safe_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if (not url.startswith("/") or url.startswith("//") or parsed.scheme or parsed.netloc
            or "\\" in url or any(ord(c) < 32 for c in url) or len(url) > 255):
        raise HTTPException(422, "menu.url_invalid")
    return url


def menu_public(m: MenuItem) -> dict:
    from app.core.i18n import t
    return {"id": m.id, "label": m.label or t(m.label_key), "url": m.url, "icon": m.icon,
            "role": m.role, "order": m.sort_order, "enabled": m.enabled,
            "plugin_id": m.plugin_id, "editable": m.plugin_id is None}


async def save_menu(db, data: dict, menu_id: int | None = None) -> MenuItem:
    label = data["label"].strip()
    if not label or len(label) > 120 or data["role"] not in ("",) + ROLES or data["icon"] not in ICONS:
        raise HTTPException(422, "err.field_invalid")
    url = safe_url(data["url"])
    if not 0 <= data["order"] <= 1000:
        raise HTTPException(422, "customization.order_invalid")
    row = None
    if menu_id is not None:
        row = (await db.execute(select(MenuItem).where(MenuItem.id == menu_id))).scalar_one_or_none()
        if row is None or row.plugin_id is not None:
            raise HTTPException(404, "menu.not_editable")
    if row is None:
        row = MenuItem(label_key="")
        db.add(row)
    row.label, row.url, row.icon = label, url, data["icon"]
    row.role, row.sort_order, row.enabled = data["role"], data["order"], data["enabled"]
    await db.flush()
    return row
