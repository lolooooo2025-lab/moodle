"""Capability-based authorization — Moodle's model, re-implemented.

Resolution order (Moodle accesslib.php:788): any PROHIBIT wins; otherwise an
ALLOW grants; PREVENT is a soft deny that a lower-context ALLOW can override.
Here we resolve: user overrides first (prohibit wins), then role grants, then
the catalogue default. AuthZ is data, not `if role == 'admin'`.
"""
from __future__ import annotations
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RoleCapability, UserCapabilityOverride, User

# The capability catalogue. Each entry: risk bitmask-ish metadata + default role grants.
# captype: read | write | manage.  Defaults grant to roles listed.
TT_CAPABILITIES: dict[str, dict] = {
    # site / admin
    "site/manage":            {"captype": "manage", "roles": ["owner"]},
    "site/settings":          {"captype": "manage", "roles": ["owner", "admin"]},
    "site/security":          {"captype": "manage", "roles": ["owner"]},
    "plugin/manage":          {"captype": "manage", "roles": ["owner", "admin"]},
    "plugin/purge":           {"captype": "manage", "roles": ["owner"]},
    "user/manage":            {"captype": "manage", "roles": ["owner", "admin", "moderator"]},
    "user/ban":               {"captype": "manage", "roles": ["owner", "admin", "moderator"]},
    "user/force_logout":      {"captype": "manage", "roles": ["owner", "admin"]},
    "audit/view":             {"captype": "read",   "roles": ["owner", "admin"]},
    "task/manage":            {"captype": "manage", "roles": ["owner", "admin"]},
    "task/run":               {"captype": "manage", "roles": ["owner", "admin"]},
    "backup/manage":          {"captype": "manage", "roles": ["owner"]},
    "report/view":            {"captype": "read",   "roles": ["owner", "admin", "moderator", "teacher"]},
    # content
    "course/create":          {"captype": "write",  "roles": ["owner", "admin", "teacher"]},
    "course/edit":            {"captype": "write",  "roles": ["owner", "admin", "teacher"]},
    "course/delete":          {"captype": "write",  "roles": ["owner", "admin"]},
    "course/pricing":         {"captype": "manage", "roles": ["owner", "admin"]},
    "course/purge":           {"captype": "manage", "roles": ["owner"]},
    "lesson/edit":            {"captype": "write",  "roles": ["owner", "admin", "teacher"]},
    "library/moderate":       {"captype": "manage", "roles": ["owner", "admin", "moderator"]},
    "library/upload":         {"captype": "write",  "roles": ["owner", "admin", "teacher", "student"]},
    "exam/create":            {"captype": "write",  "roles": ["owner", "admin", "teacher"]},
    "exam/grade":             {"captype": "write",  "roles": ["owner", "admin", "teacher"]},
    "exam/take":              {"captype": "write",  "roles": ["owner", "admin", "teacher", "student"]},
    # communication
    "chat/send":              {"captype": "write",  "roles": ["owner", "admin", "moderator", "teacher", "student"]},
    "message/send":           {"captype": "write",  "roles": ["owner", "admin", "moderator", "teacher", "student"]},
    "forum/post":             {"captype": "write",  "roles": ["owner", "admin", "moderator", "teacher", "student"]},
    "moderation/review":      {"captype": "manage", "roles": ["owner", "admin", "moderator"]},
    "sticker/approve":        {"captype": "manage", "roles": ["owner", "admin", "moderator"]},
    # money / broadcast / live
    "purchase/confirm":       {"captype": "manage", "roles": ["owner", "admin"]},
    "purchase/request":       {"captype": "write",  "roles": ["owner", "admin", "teacher", "student", "parent"]},
    "broadcast/send":         {"captype": "manage", "roles": ["owner", "admin"]},
    "stream/manage":          {"captype": "manage", "roles": ["owner", "admin"]},
    "campaign/manage":        {"captype": "manage", "roles": ["owner", "admin"]},
    "stream/key":             {"captype": "manage", "roles": ["owner"]},
    # ai
    "ai/use":                 {"captype": "write",  "roles": ["owner", "admin", "teacher", "student"]},
    "ai/manage_knowledge":    {"captype": "manage", "roles": ["owner", "admin"]},
    # self
    "profile/edit":           {"captype": "write",  "roles": ["owner", "admin", "moderator", "teacher", "student", "parent"]},
}

PROHIBIT, PREVENT, ALLOW = "prohibit", "prevent", "allow"

async def tt_can(db: AsyncSession, user: User | None, capability: str) -> bool:
    """Return True if the user has the capability. Anonymous → False (except public caps)."""
    if user is None:
        return False
    if capability not in TT_CAPABILITIES:
        return False
    # 1) per-user overrides: prohibit wins immediately; allow grants; prevent denies.
    ov = (await db.execute(
        select(UserCapabilityOverride).where(
            UserCapabilityOverride.user_id == user.id,
            UserCapabilityOverride.capability == capability))).scalar_one_or_none()
    if ov is not None:
        if ov.permission == PROHIBIT:
            return False
        if ov.permission == ALLOW:
            return True
        if ov.permission == PREVENT:
            return False
    # 2) role grant from DB (admin-editable), else catalogue default.
    rc = (await db.execute(
        select(RoleCapability).where(
            RoleCapability.role == user.role,
            RoleCapability.capability == capability))).scalar_one_or_none()
    if rc is not None:
        return rc.permission == ALLOW
    return user.role in TT_CAPABILITIES[capability]["roles"]

async def require_capability(db: AsyncSession, user: User | None, capability: str):
    """Raise PermissionError if the user lacks the capability. Audited by caller."""
    if not await tt_can(db, user, capability):
        raise PermissionError(capability)

def catalogue_defaults() -> list[tuple[str, str, str]]:
    """(role, capability, permission) rows to seed role_capabilities."""
    rows = []
    for cap, meta in TT_CAPABILITIES.items():
        for role in meta["roles"]:
            rows.append((role, cap, ALLOW))
    return rows
