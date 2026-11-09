"""Scheduled-task administration, token-protected cron endpoint, backup artifacts."""
from __future__ import annotations
import hmac
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core.db import get_db
from app.core import cron, backups, ratelimit
from app.core.audit import audit
from app.api.deps import envelope, require_cap, client_ip, check_csrf
from app.models import ScheduledTask, TaskRun, BackupArtifact, Plugin, utcnow

router = APIRouter(prefix="/api", tags=["tasks"])


def task_public(task: ScheduledTask, plugin_name=""):
    return {"id": task.id, "key": task.classname, "plugin": plugin_name,
            "schedule": {name: getattr(task, name) for name, _, _ in cron.FIELDS},
            "enabled": task.enabled,
            "last_run": task.last_run.isoformat() if task.last_run else "",
            "next_run": task.next_run.isoformat() if task.next_run else "",
            "locked": bool(task.locked_until and task.locked_until > utcnow())}


@router.get("/admin/tasks")
async def tasks(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "task/manage")
    rows = (await db.execute(select(ScheduledTask, Plugin.component).outerjoin(Plugin, Plugin.id == ScheduledTask.plugin_id)
                .order_by(ScheduledTask.id))).all()
    runs = (await db.execute(select(TaskRun).order_by(TaskRun.started_at.desc()).limit(50))).scalars().all()
    return envelope(True, "", {"tasks": [task_public(t, component or "") for t, component in rows],
                               "runs": [{"id": r.id, "task": r.task_key, "status": r.status,
                                         "started_at": r.started_at.isoformat(),
                                         "finished_at": r.finished_at.isoformat() if r.finished_at else "",
                                         "detail": r.detail_json, "error": r.error_key} for r in runs]})


class ScheduleIn(BaseModel):
    minute: str = Field(max_length=100)
    hour: str = Field(max_length=100)
    day: str = Field(max_length=100)
    dayofweek: str = Field(max_length=100)
    month: str = Field(max_length=100)
    enabled: bool = True


@router.post("/admin/tasks/{task_id}")
async def update_task(task_id: int, body: ScheduleIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "task/manage")
    await check_csrf(request, sess)
    task = (await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "cron.task_not_found")
    try:
        cron.validate_schedule(body.model_dump())
    except ValueError:
        raise HTTPException(422, "cron.invalid")
    before = task_public(task)
    for name, _, _ in cron.FIELDS:
        setattr(task, name, getattr(body, name))
    task.enabled = body.enabled
    task.next_run = cron.next_run(task)
    await audit(db, action="task.updated", actor=user, entity_type="scheduled_task", entity_id=task.classname,
                before=before, after={"schedule_updated": True, "enabled": body.enabled}, ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "ok.updated", task_public(task))


@router.post("/admin/tasks/{task_id}/run")
async def run_task(task_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "task/run")
    await check_csrf(request, sess)
    run = await cron.run_now(db, task_id, actor_id=user.id)
    return envelope(run.status in ("success", "skipped"), run.error_key or "cron.finished",
                    {"id": run.id, "status": run.status, "detail": run.detail_json})


@router.post("/cron/run")
async def cron_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    provided = request.headers.get("X-Cron-Token", "")
    if not hmac.compare_digest(provided.encode("utf-8"), config.CRON_TOKEN.encode("utf-8")):
        raise HTTPException(403, "err.forbidden")
    if not await ratelimit.hit(db, f"cron:{client_ip(request)}", limit=10, window=60):
        raise HTTPException(429, "err.rate_limited")
    await db.commit()
    runs = await cron.run_due(db)
    return envelope(True, "", {"runs": [{"task": r.task_key, "status": r.status} for r in runs]})


class BackupIn(BaseModel):
    include_uploads: bool = False


@router.get("/admin/backups")
async def list_backups(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "backup/manage")
    return envelope(True, "", await backups.listing(db))


@router.post("/admin/backups")
async def create_backup(body: BackupIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "backup/manage")
    await check_csrf(request, sess)
    row = await backups.create(db, actor_id=user.id, include_uploads=body.include_uploads)
    await audit(db, action="backup.created", actor=user, entity_type="backup", entity_id=row.id,
                after={"size": row.file_size, "sha256": row.sha256, "include_uploads": row.include_uploads},
                ip=client_ip(request), severity="notice")
    await db.commit()
    return envelope(True, "backup.done", backups.public(row))


@router.get("/admin/backups/{backup_id}/download")
async def download_backup(backup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "backup/manage")
    path = await backups.resolve_download(db, backup_id)
    await audit(db, action="backup.downloaded", actor=user, entity_type="backup", entity_id=backup_id,
                after={"downloaded": True}, ip=client_ip(request), severity="notice")
    await db.commit()
    return FileResponse(path, filename=path.name, media_type="application/octet-stream",
                        headers={"Cache-Control": "private, no-store"})


@router.delete("/admin/backups/{backup_id}")
async def delete_backup(backup_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "backup/manage")
    await check_csrf(request, sess)
    row = (await db.execute(select(BackupArtifact).where(BackupArtifact.id == backup_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    path = config.BACKUP_DIR / row.file_name
    if path.parent.resolve() == config.BACKUP_DIR.resolve():
        path.unlink(missing_ok=True)
    await db.delete(row)
    await audit(db, action="backup.deleted", actor=user, entity_type="backup", entity_id=backup_id,
                after={"deleted": True}, ip=client_ip(request), severity="warning")
    await db.commit()
    return envelope(True, "ok.deleted")
