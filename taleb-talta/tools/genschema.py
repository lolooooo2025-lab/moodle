"""Generate database/schema.sql from the SQLAlchemy models (PostgreSQL DDL).

No CREATE DATABASE / USE — the importer selects the database. FK ordering is
handled by Base.metadata.sorted_tables (topological), so no errno-150 analogue.
"""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def generate() -> str:
    from app.core.db import Base
    from app import models  # noqa: register models
    from sqlalchemy.schema import CreateTable, CreateIndex
    from sqlalchemy.dialects import postgresql
    dialect = postgresql.dialect()
    ddl = []
    for table in Base.metadata.sorted_tables:
        ddl.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for idx in sorted(table.indexes, key=lambda i: i.name or ""):
            ddl.append(str(CreateIndex(idx).compile(dialect=dialect)).strip() + ";")
    return ("-- Taleb Talta schema (PostgreSQL). Import into an already-selected database.\n"
            "-- No CREATE DATABASE / USE. Generated from app/models by tools/genschema.py.\n\n"
            + "\n\n".join(ddl) + "\n")

def main():
    out = ROOT / "database" / "schema.sql"
    out.write_text(generate(), encoding="utf-8")
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
