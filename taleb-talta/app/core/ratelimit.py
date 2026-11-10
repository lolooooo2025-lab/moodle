"""Rate limiting by IP and by user (prompt §7.8).

DB-backed sliding window so it works across workers without Redis. At 300K scale
this moves to Redis (same interface), but the DB version is correct and testable.
"""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RateLimit, utcnow
from app import config

async def hit(db: AsyncSession, key: str, limit: int,
              window: int = config.RATE_WINDOW_SECONDS) -> bool:
    """Record a hit; return True if allowed, False if the limit is exceeded."""
    now = utcnow()
    row = (await db.execute(select(RateLimit).where(RateLimit.key == key))).scalar_one_or_none()
    if row is None or now - row.window_start > timedelta(seconds=window):
        if row is None:
            row = RateLimit(key=key, hits=1, window_start=now)
            db.add(row)
        else:
            row.hits = 1
            row.window_start = now
        await db.flush()
        return True
    row.hits += 1
    await db.flush()
    return row.hits <= limit

async def reset(db: AsyncSession, key: str):
    row = (await db.execute(select(RateLimit).where(RateLimit.key == key))).scalar_one_or_none()
    if row:
        row.hits = 0
        row.window_start = utcnow()
        await db.flush()
