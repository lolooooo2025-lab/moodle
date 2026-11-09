"""Apply the additive Wave-3 migration, then seed defaults and backfill channels.

Run after backing up PostgreSQL. Re-running is safe. This migration adds tables,
not columns to existing tables; schema drift is rejected rather than hidden.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from sqlalchemy import text, inspect, select
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def main():
    from app.core.db import get_engine, get_sessionmaker, Base
    from app import models
    from app.main import seed_wave3
    from sqlalchemy.schema import CreateTable
    engine = get_engine()
    async with engine.begin() as conn:
        def validate(sync_conn):
            inspector = inspect(sync_conn)
            existing = set(inspector.get_table_names())
            for table in Base.metadata.sorted_tables:
                if table.name not in existing:
                    continue
                actual = {c["name"]: c for c in inspector.get_columns(table.name)}
                for col in table.columns:
                    if col.name not in actual:
                        raise RuntimeError(f"Schema drift: {table.name}.{col.name} is missing")
                    # Compare PostgreSQL-rendered types, including length/timezone.
                    actual_type = actual[col.name]["type"].compile(sync_conn.dialect).upper()
                    expected_type = col.type.compile(sync_conn.dialect).upper()
                    # PostgreSQL's native spelling of SQLAlchemy Float.
                    expected_type = expected_type.replace("FLOAT", "DOUBLE PRECISION")
                    if actual_type != expected_type:
                        raise RuntimeError(f"Schema drift: {table.name}.{col.name} type mismatch")
            return existing
        existing = await conn.run_sync(validate)
        sql = (ROOT / "database" / "migrations" / "003_communication.sql").read_text(encoding="utf-8")
        # asyncpg prepared statements accept one command at a time. The generated
        # migration contains no semicolons inside literals or procedural bodies.
        sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
        for statement in sql.split(";"):
            if statement.strip():
                await conn.execute(text(statement))
    await seed_wave3()
    async with engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"))).scalar_one()
    await engine.dispose()
    print(f"migrate_wave3: PASS — {count} tables; defaults and division memberships ready")


if __name__ == "__main__":
    asyncio.run(main())
