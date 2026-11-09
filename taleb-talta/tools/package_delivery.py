"""Build a clean source ZIP: no private env files, storage, DB data or keys.

The archive is checked against the actual local secret values before it is
written. Secret values are never printed. Output: deliverables/taleb-talta-source.zip
"""
from __future__ import annotations
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import config

OUT = ROOT / "deliverables"
ARCHIVE = OUT / "taleb-talta-source.zip"
EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", "storage", "deliverables", ".venv", "venv", ".pytest_cache", ".ruff_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pem", ".key", ".p12", ".pfx", ".sqlite3"}


def included(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES or path.name.startswith(".env"):
        return False
    if rel.parts[0] == "config" and rel.name != "secrets.env.example":
        return False
    return path.is_file()


def secret_values() -> dict[str, str]:
    values = {
        "TT_PASSWORD_PEPPER": config.PASSWORD_PEPPER,
        "TT_SESSION_SECRET": config.SESSION_SECRET,
        "TT_CRON_TOKEN": config.CRON_TOKEN,
        "TT_STREAM_SECRET": config.STREAM_SECRET,
        "TT_VAPID_PRIVATE_KEY": config.VAPID_PRIVATE_KEY,
        "TT_OWNER_PASSWORD": config.OWNER_PASSWORD,
        "TT_GEMINI_API_KEY": config.GEMINI_API_KEY,
    }
    match = re.search(r"://[^:]+:([^@]+)@", config.DATABASE_URL)
    if match and match.group(1) not in {"postgres", "password", "DB_PASSWORD"}:
        values["TT_DATABASE_URL_PASSWORD"] = match.group(1)
    return {k: v for k, v in values.items() if v and len(v) >= 8}


def main() -> int:
    files = sorted(p for p in ROOT.rglob("*") if included(p))
    values = secret_values()
    leaks = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if "secrets.env" in rel and not rel.endswith("secrets.env.example"):
            leaks.append(f"{rel}: forbidden private filename")
        if path.stat().st_size <= 10_000_000:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, value in values.items():
                if value in text:
                    leaks.append(f"{rel}: contains {name}")
    if leaks:
        print("package_delivery: FAIL")
        for leak in leaks:
            print("  " + leak)
        return 1
    OUT.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            zf.write(path, "taleb-talta/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(ARCHIVE) as zf:
        bad = zf.testzip()
        if bad:
            print(f"package_delivery: FAIL — corrupt member {bad}")
            return 1
        members = zf.namelist()
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (OUT / "SHA256SUMS").write_text(f"{digest}  {ARCHIVE.name}\n", encoding="utf-8")
    print(f"package_delivery: PASS — {len(members)} files, {ARCHIVE.stat().st_size} bytes")
    print(f"archive: {ARCHIVE}")
    print(f"sha256: {digest}")
    print("private env/storage/database files excluded; secret-value scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
