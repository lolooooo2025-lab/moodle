"""Real PostgreSQL backups. Artifacts stay outside the web root; owner-only download."""
from __future__ import annotations
import asyncio
import hashlib
import os
import secrets
import shutil
import tarfile
from datetime import timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.engine import make_url
from app import config
from app.models import BackupArtifact, utcnow

MAX_BYTES = 2 * 1024 * 1024 * 1024


def _pg_dump() -> str:
    found = shutil.which("pg_dump")
    if found:
        return found
    try:
        import pgserver
        candidate = Path(pgserver.__file__).parent / "pginstall" / "bin" / "pg_dump"
        if candidate.is_file():
            return str(candidate)
    except ImportError:
        pass
    raise RuntimeError("pg_dump_missing")


def _dump_sync(dest: Path):
    url = make_url(config.DATABASE_URL)
    env = dict(os.environ)
    env["PGDATABASE"] = url.database or "taleb_talta"
    env["PGUSER"] = url.username or "postgres"
    env["PGPASSWORD"] = url.password or ""
    host = url.host or url.query.get("host")
    if host:
        env["PGHOST"] = str(host)
    if url.port or url.query.get("port"):
        env["PGPORT"] = str(url.port or url.query["port"])
    import subprocess
    result = subprocess.run([_pg_dump(), "--format=custom", "--no-owner", "--no-privileges",
                             "--file", str(dest)], env=env, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError("pg_dump_failed")


def _archive_sync(dump: Path, dest: Path):
    base = config.STORAGE_DIR.resolve()
    if not base.exists():
        shutil.copy2(dump, dest)
        return
    backup_root = config.BACKUP_DIR.resolve()
    total = sum(p.stat().st_size for p in base.rglob("*") if p.is_file() and not p.is_symlink()
                and p.resolve() != backup_root and backup_root not in p.resolve().parents)
    if total > MAX_BYTES:
        raise RuntimeError("backup_too_large")

    def filter_info(info):
        # tar passes archive-relative names ("storage/..."), not source paths.
        relative = info.name.removeprefix("storage").lstrip("/")
        path = (base / relative).resolve()
        if info.issym() or info.islnk() or path == backup_root or backup_root in path.parents:
            return None
        return info

    with tarfile.open(dest, "w:gz", compresslevel=6) as tar:
        tar.add(dump, arcname="database.dump")
        tar.add(base, arcname="storage", filter=filter_info)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def create(db, *, actor_id=None, include_uploads=False) -> BackupArtifact:
    if config.DEMO_MODE:
        # Free hosts have ephemeral disks: a local backup artifact would give a
        # false sense of durability. The VPS path keeps real backups enabled.
        raise HTTPException(503, "err.demo_backups_disabled")
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    suffix = ".tar.gz" if include_uploads else ".dump"
    name = f"backup-{stamp}-{secrets.token_hex(4)}{suffix}"
    row = BackupArtifact(file_name=name, include_uploads=include_uploads,
                         created_by=actor_id, status="creating")
    db.add(row)
    await db.commit()
    dest = config.BACKUP_DIR / name
    dump = config.BACKUP_DIR / f".{name}.partial"
    try:
        await asyncio.to_thread(_dump_sync, dump)
        if include_uploads:
            await asyncio.to_thread(_archive_sync, dump, dest)
        else:
            dump.replace(dest)
        size = dest.stat().st_size
        if size == 0 or size > MAX_BYTES:
            raise RuntimeError("backup_size_invalid")
        row.file_size = size
        row.sha256 = await asyncio.to_thread(_checksum, dest)
        row.status = "ready"
        await db.commit()
        return row
    except Exception:
        row.status, row.error_key = "failed", "backup.failed"
        await db.commit()
        dest.unlink(missing_ok=True)
        raise HTTPException(500, "backup.failed")
    finally:
        dump.unlink(missing_ok=True)


def public(row: BackupArtifact) -> dict:
    return {"id": row.id, "file_name": row.file_name, "size": row.file_size,
            "sha256": row.sha256, "status": row.status, "include_uploads": row.include_uploads,
            "created_at": row.created_at.isoformat()}


async def listing(db):
    rows = (await db.execute(select(BackupArtifact).order_by(BackupArtifact.created_at.desc()).limit(100))).scalars().all()
    return [public(r) for r in rows]


async def resolve_download(db, backup_id: int) -> Path:
    row = (await db.execute(select(BackupArtifact).where(BackupArtifact.id == backup_id,
                BackupArtifact.status == "ready"))).scalar_one_or_none()
    if row is None or Path(row.file_name).name != row.file_name:
        raise HTTPException(404, "err.not_found")
    path = (config.BACKUP_DIR / row.file_name).resolve()
    if config.BACKUP_DIR.resolve() not in path.parents or not path.is_file():
        raise HTTPException(404, "err.not_found")
    return path


async def cleanup(db, keep_days=30) -> dict:
    cutoff = utcnow() - timedelta(days=keep_days)
    rows = (await db.execute(select(BackupArtifact).where(BackupArtifact.created_at < cutoff))).scalars().all()
    removed = 0
    for row in rows:
        if row.status == "creating" and row.created_at > utcnow() - timedelta(hours=1):
            continue
        path = config.BACKUP_DIR / row.file_name
        if path.parent.resolve() == config.BACKUP_DIR.resolve():
            path.unlink(missing_ok=True)
        await db.delete(row)
        removed += 1
    await db.flush()
    return {"removed": removed}
