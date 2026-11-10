"""check_sql_injection — no SQL built by concatenating variables.

SQLAlchemy ORM + bound parameters are safe. This flags raw text() / execute()
calls whose SQL is an f-string, a .format() call, or a + concatenation — the
patterns that introduce injection. Static DDL constants (plugin install) are fine.
Exit 1 on any violation.
"""
from __future__ import annotations
import ast, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent

SQL_FUNCS = {"text", "execute", "exec_driver_sql"}

def is_dynamic_sql(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):           # f-string
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr in ("format", "format_map"):
        return True
    if isinstance(node, ast.Mod):                  # % formatting
        return True
    return False

def main():
    violations = []
    for p in (ROOT / "app").rglob("*.py"):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fname = ""
                if isinstance(node.func, ast.Name):
                    fname = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    fname = node.func.attr
                if fname in SQL_FUNCS and node.args:
                    if is_dynamic_sql(node.args[0]):
                        violations.append(f"{p}:{node.lineno}: dynamic SQL in {fname}()")
    if violations:
        print("check_sql_injection: FAIL — SQL built from variables:")
        for v in violations:
            print("  " + v)
        return 1
    print("check_sql_injection: PASS — no concatenated/f-string SQL in app/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
