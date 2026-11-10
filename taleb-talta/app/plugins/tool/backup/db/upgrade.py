"""Ordered upgrade steps keyed on version (Moodle db/upgrade.php pattern).

Each step runs only if its version > installed_version; the engine records a
savepoint after each so a failed upgrade resumes rather than re-runs.
"""
from sqlalchemy import text

async def _add_size_column(db):
    await db.execute(text(
        "ALTER TABLE backup_records ADD COLUMN IF NOT EXISTS size_bytes BIGINT NOT NULL DEFAULT 0"))
    await db.flush()

UPGRADES = {
    2026110501: _add_size_column,
}
