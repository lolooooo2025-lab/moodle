"""Plugin engine — the heart of "add any feature" (Moodle's model, original code).

A plugin is a package at app/plugins/<type>/<name>/ with:
  version.py        PLUGIN = {component, version, requires, dependencies, maturity}
  manifest.json     machine-readable metadata (type, name, permissions, tables)
  db/install.py     install(db) -> runs schema/seed for the plugin
  db/upgrade.py     UPGRADES = {version: async fn(db)}  ordered steps
  db/access.py      CAPABILITIES = {cap: {captype, roles}}
  db/events.py      OBSERVERS = {event_name: async fn(payload)}
  db/tasks.py       TASKS = [{classname, minute, hour, ...}]
  settings.py       SETTINGS = [{name, default, label_key, type}]
  lib.py            navigation() -> [menu items]; optional callbacks
  lang/ar.py        STRINGS = {...}

Lifecycle mirrors Moodle: present → installed → enabled (three distinct states),
savepoint-per-step upgrade, uninstall keeps data by default (purge is owner-only).
Every action is audited and capability-gated by the caller (API layer).
"""
from __future__ import annotations
import importlib
import json
import re
from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.models import (Plugin, PluginSetting, PluginEvent, ScheduledTask, MenuItem,
                        RoleCapability, utcnow)
from app.core import capabilities as caps
from app.core.audit import audit
from app.core.events import bus

PLUGINS_DIR = config.APP_DIR / "plugins"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

def _mod(component: str, sub: str):
    """Import a plugin submodule, returning None if absent."""
    ptype, pname = component.split("_", 1)
    try:
        return importlib.import_module(f"app.plugins.{ptype}.{pname}.{sub}")
    except ModuleNotFoundError:
        return None

def discover() -> list[dict]:
    """Scan the plugins directory; return metadata for every present plugin."""
    found = []
    if not PLUGINS_DIR.exists():
        return found
    for typedir in sorted(PLUGINS_DIR.iterdir()):
        if not typedir.is_dir() or typedir.name.startswith("_"):
            continue
        ptype = typedir.name
        if ptype not in caps.__dict__.get("_", []) and ptype not in [
            "block", "tool", "report", "local", "qtype", "theme", "filter",
            "auth", "enrol", "repository", "aiprovider"]:
            continue
        for plugdir in sorted(typedir.iterdir()):
            if not plugdir.is_dir() or not NAME_RE.match(plugdir.name):
                continue
            vfile = plugdir / "version.py"
            if not vfile.exists():
                continue
            component = f"{ptype}_{plugdir.name}"
            vmod = _mod(component, "version")
            meta = getattr(vmod, "PLUGIN", {}) if vmod else {}
            manifest = {}
            mfile = plugdir / "manifest.json"
            if mfile.exists():
                manifest = json.loads(mfile.read_text(encoding="utf-8"))
            found.append({
                "component": component, "type": ptype, "name": plugdir.name,
                "version": int(meta.get("version", 0)),
                "requires": int(meta.get("requires", 0)),
                "dependencies": list(meta.get("dependencies", [])),
                "maturity": meta.get("maturity", "stable"),
                "manifest": manifest,
            })
    return found

async def sync_present(db: AsyncSession) -> list[Plugin]:
    """Upsert a Plugin row (status=present) for every discovered plugin."""
    rows = []
    for meta in discover():
        row = (await db.execute(select(Plugin).where(
            Plugin.component == meta["component"]))).scalar_one_or_none()
        if row is None:
            row = Plugin(type=meta["type"], name=meta["name"],
                         component=meta["component"], disk_version=meta["version"],
                         status="present")
            db.add(row)
        else:
            row.disk_version = meta["version"]
        rows.append(row)
    await db.flush()
    return rows

def _check_dependencies(meta: dict, installed: set[str]) -> list[str]:
    return [d for d in meta.get("dependencies", []) if d not in installed]

async def install(db: AsyncSession, component: str, *, actor=None, ip: str = "") -> Plugin:
    meta = next((m for m in discover() if m["component"] == component), None)
    if meta is None:
        raise ValueError("plugin_not_found")
    row = (await db.execute(select(Plugin).where(
        Plugin.component == component))).scalar_one_or_none()
    if row is None:
        row = await _upsert_one(db, meta)
    if row.status in ("installed", "enabled"):
        return row
    # dependency check
    installed = {p.component for p in (await db.execute(select(Plugin))).scalars()
                 if p.status in ("installed", "enabled")}
    missing = _check_dependencies(meta, installed)
    if missing:
        raise ValueError("missing_dependencies:" + ",".join(missing))
    # 1) schema / seed
    inst = _mod(component, "db.install")
    if inst and hasattr(inst, "install"):
        await inst.install(db)
    # 2) capabilities
    access = _mod(component, "db.access")
    if access:
        for cap, cmeta in getattr(access, "CAPABILITIES", {}).items():
            caps.TT_CAPABILITIES[cap] = cmeta
            for role in cmeta.get("roles", []):
                exists = (await db.execute(select(RoleCapability).where(
                    RoleCapability.role == role, RoleCapability.capability == cap
                ))).scalar_one_or_none()
                if exists is None:
                    db.add(RoleCapability(role=role, capability=cap, permission="allow"))
    # 3) events
    events = _mod(component, "db.events")
    if events:
        for ev, fn in getattr(events, "OBSERVERS", {}).items():
            db.add(PluginEvent(plugin_id=row.id, event=ev,
                               observer=f"{component}:{ev}"))
            bus.subscribe(ev, fn)
    # 4) tasks
    tasks = _mod(component, "db.tasks")
    if tasks:
        for tk in getattr(tasks, "TASKS", []):
            exists = (await db.execute(select(ScheduledTask).where(
                ScheduledTask.classname == tk["classname"]))).scalar_one_or_none()
            if exists is None:
                db.add(ScheduledTask(plugin_id=row.id, **tk))
    # 5) settings defaults
    settings = _mod(component, "settings")
    if settings:
        for st in getattr(settings, "SETTINGS", []):
            exists = (await db.execute(select(PluginSetting).where(
                PluginSetting.plugin_id == row.id,
                PluginSetting.name == st["name"]))).scalar_one_or_none()
            if exists is None:
                db.add(PluginSetting(plugin_id=row.id, name=st["name"],
                                     value=str(st.get("default", ""))))
    # 6) navigation / menu
    lib = _mod(component, "lib")
    if lib and hasattr(lib, "navigation"):
        for item in lib.navigation():
            db.add(MenuItem(plugin_id=row.id, label_key=item["label_key"],
                            url=item["url"], icon=item.get("icon", ""),
                            role=item.get("role", ""), sort_order=item.get("order", 0)))
    row.status = "installed"
    row.installed_version = meta["version"]
    row.installed_at = utcnow()
    row.updated_at = utcnow()
    await db.flush()
    await audit(db, action="plugin.installed", actor=actor, entity_type="plugin",
                entity_id=component, ip=ip, severity="notice")
    await bus.dispatch("plugin.installed", {"component": component})
    return row

async def _upsert_one(db: AsyncSession, meta: dict) -> Plugin:
    row = Plugin(type=meta["type"], name=meta["name"], component=meta["component"],
                 disk_version=meta["version"], status="present")
    db.add(row)
    await db.flush()
    return row

async def enable(db: AsyncSession, component: str, *, actor=None, ip="") -> Plugin:
    row = await _get(db, component)
    # re-subscribe observers
    events = _mod(component, "db.events")
    if events:
        for ev, fn in getattr(events, "OBSERVERS", {}).items():
            bus.subscribe(ev, fn)
    row.status = "enabled"
    row.updated_at = utcnow()
    await db.flush()
    await audit(db, action="plugin.enabled", actor=actor, entity_type="plugin",
                entity_id=component, ip=ip, severity="notice")
    await bus.dispatch("plugin.enabled", {"component": component})
    return row

async def disable(db: AsyncSession, component: str, *, actor=None, ip="") -> Plugin:
    row = await _get(db, component)
    row.status = "disabled"
    row.updated_at = utcnow()
    await db.flush()
    await audit(db, action="plugin.disabled", actor=actor, entity_type="plugin",
                entity_id=component, ip=ip, severity="notice")
    await bus.dispatch("plugin.disabled", {"component": component})
    return row

async def upgrade(db: AsyncSession, component: str, *, actor=None, ip="") -> Plugin:
    row = await _get(db, component)
    meta = next((m for m in discover() if m["component"] == component), None)
    if meta is None:
        raise ValueError("plugin_not_found")
    up = _mod(component, "db.upgrade")
    steps = getattr(up, "UPGRADES", {}) if up else {}
    for ver in sorted(steps):
        if ver > row.installed_version:
            await steps[ver](db)
            row.installed_version = ver       # savepoint per step
            await db.flush()
    row.installed_version = meta["version"]
    row.disk_version = meta["version"]
    row.updated_at = utcnow()
    await db.flush()
    await audit(db, action="plugin.upgraded", actor=actor, entity_type="plugin",
                entity_id=component, after={"version": meta["version"]}, ip=ip, severity="notice")
    await bus.dispatch("plugin.upgraded", {"component": component})
    return row

async def uninstall(db: AsyncSession, component: str, *, purge: bool = False,
                    actor=None, ip="") -> None:
    row = await _get(db, component)
    # remove menu / settings / events / tasks (never user data unless purge)
    await db.execute(delete(MenuItem).where(MenuItem.plugin_id == row.id))
    await db.execute(delete(PluginSetting).where(PluginSetting.plugin_id == row.id))
    await db.execute(delete(PluginEvent).where(PluginEvent.plugin_id == row.id))
    await db.execute(delete(ScheduledTask).where(ScheduledTask.plugin_id == row.id))
    if purge:
        inst = _mod(component, "db.install")
        if inst and hasattr(inst, "purge"):
            await inst.purge(db)
    row.status = "present"
    row.installed_version = 0
    row.updated_at = utcnow()
    await db.flush()
    await audit(db, action="plugin.uninstalled", actor=actor, entity_type="plugin",
                entity_id=component, after={"purge": purge}, ip=ip,
                severity="warning" if purge else "notice")
    await bus.dispatch("plugin.uninstalled", {"component": component, "purge": purge})

async def _get(db: AsyncSession, component: str) -> Plugin:
    row = (await db.execute(select(Plugin).where(
        Plugin.component == component))).scalar_one_or_none()
    if row is None:
        raise ValueError("plugin_not_found")
    return row

async def load_enabled_observers(db: AsyncSession):
    """On boot, re-subscribe observers for all enabled plugins."""
    rows = (await db.execute(select(Plugin).where(Plugin.status == "enabled"))).scalars().all()
    for row in rows:
        events = _mod(row.component, "db.events")
        if events:
            for ev, fn in getattr(events, "OBSERVERS", {}).items():
                bus.subscribe(ev, fn)
        access = _mod(row.component, "db.access")
        if access:
            for cap, cmeta in getattr(access, "CAPABILITIES", {}).items():
                caps.TT_CAPABILITIES[cap] = cmeta


async def settings_for(db, component: str) -> list[dict]:
    row = await _get(db, component)
    mod = _mod(component, "settings")
    specs = getattr(mod, "SETTINGS", []) if mod else []
    values = {s.name: s.value for s in (await db.execute(select(PluginSetting).where(
        PluginSetting.plugin_id == row.id))).scalars()}
    return [{"name": s["name"], "label_key": s.get("label_key", s["name"]),
             "type": s.get("type", "text"), "value": values.get(s["name"], str(s.get("default", ""))),
             "min": s.get("min", 0), "max": s.get("max", 100000)} for s in specs]


async def save_settings(db, component: str, values: dict, *, actor=None, ip="") -> list[dict]:
    row = await _get(db, component)
    if row.status == "present":
        raise ValueError("plugin_not_installed")
    mod = _mod(component, "settings")
    specs = {s["name"]: s for s in (getattr(mod, "SETTINGS", []) if mod else [])}
    if set(values) - set(specs):
        raise ValueError("plugin_setting_unknown")
    cleaned = {}
    for name, value in values.items():
        spec = specs[name]
        kind = spec.get("type", "text")
        if kind == "bool":
            if str(value) not in ("0", "1") and not isinstance(value, bool):
                raise ValueError("plugin_setting_invalid")
            cleaned[name] = "1" if value in (True, "1", 1) else "0"
        elif kind == "int":
            try:
                number = int(value)
            except (TypeError, ValueError):
                raise ValueError("plugin_setting_invalid")
            low, high = spec.get("min", 0), spec.get("max", 100000)
            if not low <= number <= high:
                raise ValueError("plugin_setting_invalid")
            cleaned[name] = str(number)
        else:
            text = str(value).strip()
            if len(text) > 1000:
                raise ValueError("plugin_setting_invalid")
            cleaned[name] = text
    before = {s["name"]: s["value"] for s in await settings_for(db, component)}
    for name, value in cleaned.items():
        setting = (await db.execute(select(PluginSetting).where(
            PluginSetting.plugin_id == row.id, PluginSetting.name == name))).scalar_one_or_none()
        if setting is None:
            db.add(PluginSetting(plugin_id=row.id, name=name, value=value))
        else:
            setting.value = value
    await audit(db, action="plugin.settings_updated", actor=actor, entity_type="plugin", entity_id=component,
                before=before, after=cleaned, ip=ip, severity="notice")
    await db.flush()
    await bus.dispatch("plugin.settings_updated", {"component": component, "keys": list(cleaned)})
    return await settings_for(db, component)
