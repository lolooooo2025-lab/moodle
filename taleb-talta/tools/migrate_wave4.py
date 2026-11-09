"""Apply the additive Wave-4 migration, then seed builder/cron defaults.

Safe to re-run. Existing data is preserved; pre-W4 column drift is rejected.
Run before migrate_wave3 on an older database (the shared model metadata now
includes W4 columns). Fresh schema.sql installs already contain everything.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text, inspect, select
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NEW_TABLES = {"custom_fields", "custom_field_values", "dashboard_blocks", "dashboard_preferences",
              "theme_presets", "role_themes", "task_runs", "digest_deliveries", "backup_artifacts"}
NEW_COLUMNS = {("menu_items", "label"), ("scheduled_tasks", "lock_token"), ("scheduled_tasks", "locked_until")}


async def main():
    from app.core.db import get_engine, get_sessionmaker, Base
    from app import models
    from app.core.capabilities import catalogue_defaults
    from app.core import customization, cron
    engine = get_engine()
    async with engine.begin() as conn:
        def validate(sync_conn):
            inspector = inspect(sync_conn)
            existing = set(inspector.get_table_names())
            for table in Base.metadata.sorted_tables:
                if table.name not in existing or table.name in NEW_TABLES:
                    continue
                actual = {c["name"]: c for c in inspector.get_columns(table.name)}
                for col in table.columns:
                    if (table.name, col.name) in NEW_COLUMNS:
                        continue
                    if col.name not in actual:
                        raise RuntimeError(f"Schema drift: {table.name}.{col.name} is missing")
                    actual_type = actual[col.name]["type"].compile(sync_conn.dialect).upper()
                    expected_type = col.type.compile(sync_conn.dialect).upper().replace("FLOAT", "DOUBLE PRECISION")
                    if actual_type != expected_type:
                        raise RuntimeError(f"Schema drift: {table.name}.{col.name} type mismatch")
            return existing
        await conn.run_sync(validate)
        sql = (ROOT / "database" / "migrations" / "004_administration.sql").read_text(encoding="utf-8")
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                await conn.execute(text(statement))
    async with get_sessionmaker()() as db:
        for role, cap, perm in catalogue_defaults():
            exists = (await db.execute(select(models.RoleCapability).where(
                models.RoleCapability.role == role, models.RoleCapability.capability == cap))).first()
            if exists is None:
                db.add(models.RoleCapability(role=role, capability=cap, permission=perm))
        await customization.seed_defaults(db)
        await cron.seed_tasks(db)
        await db.commit()
    async with engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))).scalar_one()
    await engine.dispose()
    print(f"migrate_wave4: PASS — {count} tables; settings/builders/cron defaults ready")


if __name__ == "__main__":
    asyncio.run(main())
