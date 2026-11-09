"""Build a clean free-demo deployment ZIP (Render free web + Neon free Postgres).

The archive is ready to upload to a GitHub repository root: render.yaml sits at
the top level. Private env files, storage, databases, keys, and development
artifacts are excluded, and the archive is scanned against local private secret
values before it is written. Values are never printed.
"""
from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
ARCHIVE = OUT / "taleb-talta-free-demo.zip"
PREFIX = "taleb-talta/"

INCLUDE_DIRS = ("app", "database", "deploy/free-demo")
INCLUDE_ROOT = {
    ".gitignore",
    "requirements.txt",
    "requirements.lock.txt",
    "FREE_DEMO.md",
}
INCLUDE_CONFIG = {"secrets.env.example", "free-demo.env.example"}
EXCLUDE_DIRS = {"__pycache__", "storage", ".venv", "venv", "node_modules", ".git"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".sqlite3", ".dump"}
PLACEHOLDER = re.compile(r"REPLACE_|example\.com|DB_USER|DB_PASSWORD|DB_HOST|DB_NAME", re.I)


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES or path.name.startswith(".env"):
        return False
    if rel.parts[0] == "config":
        return len(rel.parts) == 2 and rel.name in INCLUDE_CONFIG
    if rel.parts[0] == "deploy":
        return rel.parts[:2] == ("deploy", "free-demo") and path.is_file()
    if rel.parts[0] in INCLUDE_DIRS:
        return path.is_file()
    return len(rel.parts) == 1 and rel.name in INCLUDE_ROOT and path.is_file()


def private_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for name in ("secrets.env", "production.env"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, raw = line.split("=", 1)
            key = key.strip()
            val = raw.strip().strip('"').strip("'")
            if not val or len(val) < 8 or PLACEHOLDER.search(val):
                continue
            if val in {"postgres", "password", "DB_PASSWORD"}:
                continue
            values[f"{name}:{key}"] = val
        text = path.read_text(encoding="utf-8")
        match = re.search(r"TT_DATABASE_URL=([^\n]+)", text)
        if match:
            url = match.group(1).strip().strip('"').strip("'")
            pw = re.search(r"://[^:]+:([^@]+)@", url)
            if pw and pw.group(1) not in {"postgres", "password", "DB_PASSWORD"}:
                values[f"{name}:TT_DATABASE_URL_PASSWORD"] = pw.group(1)
    return values


def main() -> int:
    files = sorted(p for p in ROOT.rglob("*") if included(p))
    required = [
        ROOT / "deploy/free-demo/render.yaml",
        ROOT / "deploy/free-demo/start.py",
        ROOT / "FREE_DEMO.md",
        ROOT / "requirements.lock.txt",
        ROOT / "config/free-demo.env.example",
        ROOT / "app/main.py",
        ROOT / "database/schema.sql",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        print("package_free_demo: FAIL — missing required files:")
        for name in missing:
            print("  " + name)
        return 1

    values = private_env_values()
    leaks: list[str] = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith(("secrets.env", "production.env")) or "/storage/" in rel:
            leaks.append(f"{rel}: forbidden private member")
        if path.stat().st_size <= 10_000_000:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, value in values.items():
                if value in text:
                    leaks.append(f"{rel}: contains private value from {name}")
    if leaks:
        print("package_free_demo: FAIL")
        for leak in leaks:
            print("  " + leak)
        return 1

    OUT.mkdir(exist_ok=True)
    digest = hashlib.sha256()
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            zf.write(path, PREFIX + rel)
        # Blueprint must be at the repository root for Render to discover it.
        zf.write(ROOT / "deploy/free-demo/render.yaml", PREFIX + "render.yaml")

    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (OUT / "FREE_DEMO_SHA256SUMS").write_text(
        f"{digest}  {ARCHIVE.name}\n", encoding="utf-8"
    )
    with zipfile.ZipFile(ARCHIVE) as zf:
        count = len(zf.namelist())
    print(f"package_free_demo: PASS — {count} files, {ARCHIVE.stat().st_size} bytes")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
