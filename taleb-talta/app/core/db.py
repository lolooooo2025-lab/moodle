"""Async SQLAlchemy engine + session factory (PostgreSQL via asyncpg).

One clock everywhere: the app uses timezone-aware UTC datetimes; PostgreSQL
columns are TIMESTAMPTZ so there is no PHP-vs-MySQL-style timezone mismatch
(the prompt's trap #2). All expiry comparisons happen in Python against UTC.
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import MetaData
from app import config

# Naming convention so constraints/indexes have deterministic names (clean migrations).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

_engine = None
_sessionmaker = None

def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            config.DATABASE_URL,
            echo=False,
            pool_size=config.DB_POOL_SIZE,
            max_overflow=config.DB_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine

def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
    return _sessionmaker

async def get_db() -> AsyncSession:
    """FastAPI dependency yielding a session."""
    async with get_sessionmaker()() as session:
        yield session

async def init_db():
    """Create all tables (dev/test). Production uses database/schema.sql migrations."""
    from app import models  # noqa: F401  (register models)
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def dispose_db():
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
