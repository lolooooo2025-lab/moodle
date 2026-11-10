"""Plugin schema install + purge (Moodle db/install.xml + uninstall pattern).

The plugin owns its own table (backup_records). Install creates it; purge drops
it (owner-only, audited by the engine). User data is never dropped on a normal
uninstall — only on explicit purge.
"""
from sqlalchemy import text

CREATE = """
CREATE TABLE IF NOT EXISTS backup_records (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind VARCHAR(40) NOT NULL DEFAULT 'manual',
    status VARCHAR(20) NOT NULL DEFAULT 'ok',
    note TEXT NOT NULL DEFAULT ''
)
"""

async def install(db):
    await db.execute(text(CREATE))
    await db.flush()

async def purge(db):
    await db.execute(text("DROP TABLE IF EXISTS backup_records"))
    await db.flush()
