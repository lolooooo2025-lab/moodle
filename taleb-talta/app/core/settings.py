"""Typed, allow-listed site settings. No secrets or arbitrary Python are stored here."""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from app import config
from app.models import SiteSetting


@dataclass(frozen=True)
class SettingSpec:
    group: str
    kind: str
    default: str
    minimum: int = 0
    maximum: int = 0
    capability: str = "site/settings"


SPECS = {
    "site.name": SettingSpec("general", "text", ""),
    "site.contact_phone": SettingSpec("general", "text", ""),
    "site.contact_message": SettingSpec("general", "text", ""),
    "site.registration_enabled": SettingSpec("registration", "bool", "1"),
    "site.maintenance": SettingSpec("registration", "bool", "0"),
    "security.login_max_account": SettingSpec("security", "int", str(config.LOGIN_MAX_PER_ACCOUNT), 4, 20, "site/security"),
    "security.login_max_ip": SettingSpec("security", "int", str(config.LOGIN_MAX_PER_IP), 10, 100, "site/security"),
    "security.lockout_minutes": SettingSpec("security", "int", str(config.LOCKOUT_SECONDS // 60), 5, 60, "site/security"),
    "security.session_idle_minutes": SettingSpec("security", "int", str(config.SESSION_IDLE_SECONDS // 60), 5, 60, "site/security"),
    "security.session_absolute_hours": SettingSpec("security", "int", str(config.SESSION_ABSOLUTE_SECONDS // 3600), 1, 12, "site/security"),
    "security.password_min_length": SettingSpec("security", "int", str(config.PASSWORD_MIN_LENGTH), 12, 32, "site/security"),
    "security.password_history": SettingSpec("security", "int", str(config.PASSWORD_HISTORY), 3, 10, "site/security"),
}


def validate(key: str, value) -> str:
    if key not in SPECS:
        raise ValueError("admin.setting_unknown")
    spec = SPECS[key]
    if spec.kind == "bool":
        if isinstance(value, bool):
            return "1" if value else "0"
        if str(value) in ("0", "1"):
            return str(value)
        raise ValueError("err.field_invalid")
    if spec.kind == "int":
        if isinstance(value, bool):
            raise ValueError("err.field_invalid")
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("err.field_invalid")
        if not spec.minimum <= n <= spec.maximum:
            raise ValueError("admin.setting_range")
        return str(n)
    text = str(value).strip()
    limit = 1000 if key.endswith("message") else 160
    if len(text) > limit or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError("err.field_invalid")
    if key.endswith("phone") and text:
        from app.core.auth import valid_phone, normalize_phone
        text = normalize_phone(text)
        if not valid_phone(text):
            raise ValueError("err.invalid_phone")
    return text


async def raw(db, key: str, default: str = "") -> str:
    row = (await db.execute(select(SiteSetting).where(SiteSetting.key == key))).scalar_one_or_none()
    return row.value if row else default


async def boolean(db, key: str) -> bool:
    return (await raw(db, key, SPECS[key].default)) == "1"


async def integer(db, key: str) -> int:
    spec = SPECS[key]
    try:
        value = int(await raw(db, key, spec.default))
    except ValueError:
        return int(spec.default)
    return value if spec.minimum <= value <= spec.maximum else int(spec.default)


async def security_policy(db) -> dict:
    return {key: await integer(db, key) for key in SPECS if key.startswith("security.")}


async def public_values(db) -> dict:
    return {key: await raw(db, key, spec.default) for key, spec in SPECS.items()
            if spec.capability != "site/security"}


async def save(db, values: dict, *, actor, ip: str = "") -> dict:
    from app.core.audit import audit
    from app.core.events import bus
    # Validate the whole batch before changing anything.
    cleaned = {key: validate(key, value) for key, value in values.items()}
    before, after = {}, {}
    for key, value in cleaned.items():
        old = await raw(db, key, SPECS[key].default)
        row = (await db.execute(select(SiteSetting).where(SiteSetting.key == key))).scalar_one_or_none()
        if row is None:
            row = SiteSetting(key=key, value=value)
            db.add(row)
        else:
            row.value = value
        before[key], after[key] = old, value
    await audit(db, action="settings.updated", actor=actor, entity_type="site_settings",
                entity_id="batch", before=before, after=after, ip=ip, severity="notice")
    await db.commit()
    await bus.dispatch("settings.updated", {"keys": list(cleaned)})
    return after
