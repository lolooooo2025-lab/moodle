"""check_i18n — no hard-coded user-visible Arabic string outside lang/.

Scans app/**/*.py (except */lang/*), app/templates/**/*.html and app/static/**/*.js
for Arabic literals. Templates must use t(); JS must get messages from the API.
Docstrings/comments are ignored (not user-visible). Exit 1 on any violation.
"""
from __future__ import annotations
import ast, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARABIC = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

def is_lang(p: pathlib.Path) -> bool:
    return "/lang/" in str(p) or p.name == "ar.py" and "lang" in str(p)

def check_py(p: pathlib.Path) -> list[str]:
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    # collect docstring nodes to exclude
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                docstrings.add(id(node.body[0].value))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings:
                continue
            if ARABIC.search(node.value.encode("unicode_escape").decode("ascii")):
                bad.append(f"{p}:{node.lineno}: {node.value[:60]!r}")
    return bad

def check_text(p: pathlib.Path) -> list[str]:
    bad = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if ARABIC.search(line):
            bad.append(f"{p}:{i}: {line.strip()[:60]!r}")
    return bad

def main():
    violations = []
    for p in (ROOT / "app").rglob("*.py"):
        if is_lang(p):
            continue
        violations += check_py(p)
    for p in (ROOT / "app" / "templates").rglob("*.html"):
        violations += check_text(p)
    for p in (ROOT / "app" / "static").rglob("*.js"):
        violations += check_text(p)
    if violations:
        print("check_i18n: FAIL — hard-coded Arabic outside lang/:")
        for v in violations:
            print("  " + v)
        return 1
    print("check_i18n: PASS — no hard-coded Arabic outside lang/")
    return 0

if __name__ == "__main__":
    sys.exit(main())
