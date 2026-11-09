"""Build a clean deployment/upload ZIP.

Includes only production source, migrations, deployment scripts, pinned
requirements, and delivery docs. Private env files, storage, databases, keys,
and development screenshots are excluded. The archive is scanned against local
private secret values before it is written; values are never printed.
"""
from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
ARCHIVE = OUT / "taleb-talta-upload.zip"

INCLUDE_DIRS = ("app", "database", "deploy")
INCLUDE_TOOLS = {
    "check_production_config.py",
    "check_served_secrets.py",
    "check_live_schema.py",
    "migrate_wave3.py",
    "migrate_wave4.py",
    "migrate_wave5.py",
}
INCLUDE_ROOT = {
    ".gitignore",
    "requirements.txt",
    "requirements.lock.txt",
    "UPLOAD.md",
}
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
        return rel.as_posix() == "config/secrets.env.example"
    if rel.parts[0] == "tools":
        return len(rel.parts) == 2 and rel.name in INCLUDE_TOOLS
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
            if key in {"TT_PUBLIC_ORIGIN", "TT_VAPID_SUBJECT", "TT_DATABASE_URL"}:
                # These are deployment-specific; avoid accidental inclusion too.
                values[f"{name}:{key}"] = val
                continue
            if val in {"postgres", "password", "DB_PASSWORD"}:
                continue
            values[f"{name}:{key}"] = val
    for name in ("secrets.env", "production.env"):
        path = ROOT / "config" / name
        if not path.exists():
            continue
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
        ROOT / "deploy/install.sh",
        ROOT / "deploy/update.sh",
        ROOT / "deploy/rollback.sh",
        ROOT / "deploy/backup.sh",
        ROOT / "deploy/common.sh",
        ROOT / "deploy/systemd/taleb-talta.service.template",
        ROOT / "deploy/systemd/taleb-talta-cron.service.template",
        ROOT / "deploy/nginx/taleb-talta.conf.template",
        ROOT / "requirements.lock.txt",
        ROOT / "UPLOAD.md",
        ROOT / "config/secrets.env.example",
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing:
        print("package_upload: FAIL — missing required files:")
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
        print("package_upload: FAIL")
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
            print(f"package_upload: FAIL — corrupt member {bad}")
            return 1
        members = zf.namelist()
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    (OUT / "UPLOAD_SHA256SUMS").write_text(f"{digest}  {ARCHIVE.name}\n", encoding="utf-8")
    print(f"package_upload: PASS — {len(members)} files, {ARCHIVE.stat().st_size} bytes")
    print(f"archive: {ARCHIVE}")
    print(f"sha256: {digest}")
    print("private env/storage/database files excluded; secret-value scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
