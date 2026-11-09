"""check_enum_values — every literal written to an ENUM column is in the allowed list.

An out-of-range ENUM write is silently truncated in MySQL; PostgreSQL with a CHECK
constraint rejects it, but we still verify statically. Builds field->allowed-values
from the models, then scans app code for string literals assigned to those fields.
Also validates every model column default. Exit 1 on any out-of-range value.
"""
from __future__ import annotations
import ast, sys, pathlib
from collections import defaultdict
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    from app.core.db import Base
    from app import models  # noqa: register models
    from sqlalchemy import Enum as SAEnum
    # field name -> union of allowed values across tables
    field_values = defaultdict(set)
    bad_defaults = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, SAEnum):
                allowed = set(col.type.enums)
                field_values[col.name] |= allowed
                if col.default is not None and getattr(col.default, "is_scalar", False):
                    if col.default.arg not in allowed:
                        bad_defaults.append(f"{table.name}.{col.name} default={col.default.arg!r}")
    violations = list(bad_defaults)
    # scan app code for keyword/attribute assignments of string literals to enum fields
    for p in (ROOT / "app").rglob("*.py"):
        if "/lang/" in str(p):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # keyword args: Model(status="x"), .values(role="y"), audit(severity="z")
            if isinstance(node, ast.keyword) and node.arg in field_values:
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    if node.value.value not in field_values[node.arg]:
                        violations.append(f"{p}:{node.lineno}: {node.arg}={node.value.value!r}")
            # attribute assignment: obj.status = "x"
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Attribute) and tgt.attr in field_values:
                        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            if node.value.value not in field_values[tgt.attr]:
                                violations.append(f"{p}:{node.lineno}: {tgt.attr}={node.value.value!r}")
    if violations:
        print("check_enum_values: FAIL — out-of-range ENUM literals:")
        for v in violations:
            print("  " + v)
        return 1
    print(f"check_enum_values: PASS — {len(field_values)} enum fields, all literals valid")
    return 0

if __name__ == "__main__":
    sys.exit(main())
