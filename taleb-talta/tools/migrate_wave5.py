"""Apply Wave 5 PostgreSQL migration, verify schema, seed scheduled jobs."""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
from sqlalchemy import text, select, func
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.db import get_engine, get_sessionmaker, dispose_db
from app.models import Purchase, Campaign, Notification, NotificationRecipient, PushSubscription, LiveStream

async def main():
    sql = (ROOT / "database/migrations/005_wave5.sql").read_text()
    try:
        async with get_engine().begin() as conn:
            sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
            for statement in sql.split(";"):
                if statement.strip():
                    await conn.execute(text(statement))
        async with get_sessionmaker()() as db:
            for model in (Purchase, Campaign, Notification, NotificationRecipient, PushSubscription, LiveStream):
                await db.execute(select(func.count()).select_from(model))
            from app.core import cron
            from app.core.capabilities import catalogue_defaults
            from app.models import RoleCapability
            for role, cap, perm in catalogue_defaults():
                if not (await db.execute(select(RoleCapability.id).where(RoleCapability.role == role,
                        RoleCapability.capability == cap))).first():
                    db.add(RoleCapability(role=role, capability=cap, permission=perm))
            await cron.seed_tasks(db)
            await db.commit()
        print("WAVE5 MIGRATION OK: purchases, notifications, campaigns, push subscriptions, live streams")
    finally:
        await dispose_db()

if __name__ == "__main__":
    asyncio.run(main())
