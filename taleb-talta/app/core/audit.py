"""Append-only audit log. Every security-relevant action is recorded.

Severity is an ENUM (info/notice/warning/critical) so the DB rejects invalid
values. The table has no UPDATE/DELETE path in code — append only.
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditLog, User

async def audit(db: AsyncSession, *, action: str, actor: User | None = None,
                actor_id: int | None = None, actor_role: str = "",
                entity_type: str = "", entity_id: str = "",
                before: dict | None = None, after: dict | None = None,
                ip: str = "", user_agent: str = "", severity: str = "info"):
    entry = AuditLog(
        actor_id=actor.id if actor else actor_id,
        actor_role=actor.role if actor else actor_role,
        action=action, entity_type=entity_type, entity_id=str(entity_id),
        before_json=before, after_json=after, ip=ip, user_agent=user_agent[:255],
        severity=severity,
    )
    db.add(entry)
    await db.flush()
    return entry
