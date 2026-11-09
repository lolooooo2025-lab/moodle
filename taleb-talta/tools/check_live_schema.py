"""Compare the live PostgreSQL schema with the ORM contract.

Static schema.sql equality is not enough: a hand-written migration can create a
running database that the ORM cannot safely use. This checks column types and
nullability, primary/unique/foreign keys, CHECK expressions and indexes (including
partial-index predicates). PostgreSQL-side DEFAULT conveniences are intentionally
ignored because the ORM supplies defaults in Python.
"""
from __future__ import annotations
import asyncio, re, sys
from pathlib import Path
from sqlalchemy import inspect
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.db import get_engine, Base, dispose_db
from app import models  # noqa: register metadata


def _norm(value: str) -> str:
    value = str(value).lower()
    value = re.sub(r"::(character varying|text|integer|bigint|boolean|double precision)(\[\])?", "", value)
    value = value.replace("= any (array[", "in (").replace("])", ")")
    value = re.sub(r"(?<![A-Za-z0-9_])[a-z_][a-z0-9_]*\.(?=[a-z_])", "", value)
    return re.sub(r"[\s()]", "", value)


def _fk_options(options: dict) -> tuple:
    return (str(options.get("ondelete") or "no action").lower(),
            str(options.get("onupdate") or "no action").lower(),
            str(options.get("deferrable") or "").lower(),
            str(options.get("initially") or "").lower())


def validate(sync_conn) -> list[str]:
    inspector = inspect(sync_conn)
    dialect = sync_conn.dialect
    existing = set(inspector.get_table_names())
    errors: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            errors.append(f"missing table {table.name}")
            continue
        actual_cols = {c["name"]: c for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name not in actual_cols:
                errors.append(f"{table.name}.{col.name}: missing column")
                continue
            actual = actual_cols[col.name]
            expected_type = col.type.compile(dialect).upper().replace("FLOAT", "DOUBLE PRECISION")
            actual_type = actual["type"].compile(dialect).upper()
            if actual_type != expected_type:
                errors.append(f"{table.name}.{col.name}: type {actual_type} != {expected_type}")
            if bool(actual["nullable"]) != bool(col.nullable):
                errors.append(f"{table.name}.{col.name}: nullable mismatch")
        pk = inspector.get_pk_constraint(table.name)
        expected_pk = table.primary_key
        if pk.get("name") != expected_pk.name or pk.get("constrained_columns") != [c.name for c in expected_pk.columns]:
            errors.append(f"{table.name}: primary key mismatch")
        actual_uq = {u["name"]: u["column_names"] for u in inspector.get_unique_constraints(table.name)}
        for constraint in table.constraints:
            kind = constraint.__class__.__name__
            if kind == "UniqueConstraint":
                if actual_uq.get(constraint.name) != [c.name for c in constraint.columns]:
                    errors.append(f"{table.name}.{constraint.name}: unique columns mismatch")
            elif kind == "CheckConstraint":
                checks = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints(table.name)}
                expected = str(constraint.sqltext.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
                if constraint.name not in checks or _norm(checks[constraint.name]) != _norm(expected):
                    errors.append(f"{table.name}.{constraint.name}: check expression mismatch")
            elif kind == "ForeignKeyConstraint":
                fks = {f["name"]: f for f in inspector.get_foreign_keys(table.name)}
                fk = fks.get(constraint.name)
                expected = ([e.parent.name for e in constraint.elements],
                            constraint.elements[0].column.table.name,
                            [e.column.name for e in constraint.elements],
                            _fk_options({"ondelete": constraint.ondelete, "onupdate": constraint.onupdate}))
                if fk is None:
                    errors.append(f"{table.name}.{constraint.name}: missing foreign key")
                else:
                    actual = (fk["constrained_columns"], fk["referred_table"], fk["referred_columns"], _fk_options(fk.get("options", {})))
                    if actual != expected:
                        errors.append(f"{table.name}.{constraint.name}: foreign key mismatch")
        actual_idx = {i["name"]: i for i in inspector.get_indexes(table.name) if not i.get("duplicates_constraint")}
        for idx in table.indexes:
            got = actual_idx.get(idx.name)
            where = idx.dialect_options.get("postgresql", {}).get("where")
            expected_where = _norm(str(where.compile(dialect=dialect))) if where is not None else ""
            if got is None:
                errors.append(f"{table.name}.{idx.name}: missing index")
                continue
            actual_where = _norm(got.get("dialect_options", {}).get("postgresql_where") or "")
            if (bool(got["unique"]) != bool(idx.unique) or got["column_names"] != [c.name for c in idx.columns]
                    or actual_where != expected_where):
                errors.append(f"{table.name}.{idx.name}: index definition mismatch")
    return errors


async def main() -> int:
    try:
        async with get_engine().connect() as conn:
            errors = await conn.run_sync(validate)
        if errors:
            print("check_live_schema: FAIL")
            for error in errors[:80]:
                print("  " + error)
            return 1
        print(f"check_live_schema: PASS — {len(Base.metadata.tables)} ORM tables match live PostgreSQL")
        return 0
    finally:
        await dispose_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
