"""check_schema_columns — the importable schema.sql is in sync with the models.

Every column the ORM reads/writes must exist in database/schema.sql. We enforce
this by regenerating the DDL from the models and comparing to the committed
schema.sql. If they differ, someone changed a model without regenerating — fail.
This is the Python/ORM analogue of "every INSERT/UPDATE column exists".
"""
from __future__ import annotations
import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

def main():
    import genschema
    expected = genschema.generate()
    path = ROOT / "database" / "schema.sql"
    if not path.exists():
        print("check_schema_columns: FAIL — database/schema.sql missing (run tools/genschema.py)")
        return 1
    actual = path.read_text(encoding="utf-8")
    if expected != actual:
        print("check_schema_columns: FAIL — schema.sql is out of sync with models.")
        print("  Run: python tools/genschema.py")
        # show a small diff hint
        import difflib
        diff = list(difflib.unified_diff(actual.splitlines(), expected.splitlines(),
                                         lineterm="", n=1))
        for line in diff[:20]:
            print("  " + line)
        return 1
    # count tables/columns for the report
    from app.core.db import Base
    from app import models  # noqa
    ntables = len(Base.metadata.tables)
    ncols = sum(len(t.columns) for t in Base.metadata.tables.values())
    print(f"check_schema_columns: PASS — schema.sql in sync ({ntables} tables, {ncols} columns)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
