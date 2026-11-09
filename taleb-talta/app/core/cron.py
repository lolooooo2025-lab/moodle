"""Database-backed cron: validated 5-field schedules, atomic claims, run history."""
from __future__ import annotations
import secrets
from datetime import timedelta
from sqlalchemy import select, update, delete, or_
from app import config
from app.models import (ScheduledTask, TaskRun, Plugin, PluginSetting, RateLimit, Session,
                        PasswordResetToken, LoginAttempt, Attachment, ChatMessage, Sticker,
                        ForumSubscription, DiscussionPost, DiscussionThread, DigestDelivery, User, utcnow)
from app.core import backups
from app.core.audit import audit
from app.core.events import bus

class _SkipTask(Exception):
    pass

FIELDS = (("minute", 0, 59), ("hour", 0, 23), ("day", 1, 31), ("dayofweek", 0, 6), ("month", 1, 12))
CORE_TASKS = {
    "core.cleanup": {"minute": "15", "hour": "3", "day": "*", "dayofweek": "*", "month": "*"},
    "core.forum_digest": {"minute": "0", "hour": "18", "day": "*", "dayofweek": "*", "month": "*"},
    "core.friday_campaign": {"minute": "*/5", "hour": "*", "day": "*", "dayofweek": "*", "month": "*"},
    "core.push_delivery": {"minute": "*", "hour": "*", "day": "*", "dayofweek": "*", "month": "*"},
}


def parse_field(value: str, low: int, high: int) -> set[int]:
    result = set()
    if not value or len(value) > 100:
        raise ValueError("cron.invalid")
    for part in value.split(","):
        chunk, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if step < 1 or step > high - low + 1:
            raise ValueError("cron.invalid")
        if chunk == "*":
            start, end = low, high
        elif "-" in chunk:
            a, b = chunk.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(chunk)
            if step_text:
                end = high
        if start < low or end > high or start > end:
            raise ValueError("cron.invalid")
        result.update(range(start, end + 1, step))
    return result


def validate_schedule(values: dict):
    for name, low, high in FIELDS:
        try:
            parse_field(str(values.get(name, "*")), low, high)
        except (ValueError, TypeError):
            raise ValueError("cron.invalid")


def next_run(task: ScheduledTask, after=None):
    sets = {name: parse_field(getattr(task, name), low, high) for name, low, high in FIELDS}
    cursor = (after or utcnow()).replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = cursor + timedelta(days=366 * 4)
    while cursor < limit:
        if cursor.month not in sets["month"]:
            cursor = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0)
            continue
        dom_ok = cursor.day in sets["day"]
        dow_ok = ((cursor.weekday() + 1) % 7) in sets["dayofweek"]
        day_ok = (dom_ok or dow_ok) if task.day != "*" and task.dayofweek != "*" else (dom_ok and dow_ok)
        if not day_ok:
            cursor = (cursor + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if cursor.hour not in sets["hour"]:
            cursor += timedelta(hours=1)
            cursor = cursor.replace(minute=0)
            continue
        if cursor.minute not in sets["minute"]:
            cursor += timedelta(minutes=1)
            continue
        return cursor
    raise ValueError("cron.no_next_run")


async def seed_tasks(db):
    for key, schedule in CORE_TASKS.items():
        row = (await db.execute(select(ScheduledTask).where(ScheduledTask.classname == key))).scalar_one_or_none()
        if row is None:
            row = ScheduledTask(classname=key, **schedule)
            row.next_run = next_run(row)
            db.add(row)
    await db.flush()


async def friday_campaign_task(db, actor_id=None):
    from app.core import notifications
    return await notifications.publish_due_campaigns(db)


async def push_delivery_task(db, actor_id=None):
    from app.core import notifications
    return await notifications.dispatch_push(db)


async def _cleanup(db, actor_id):
    now = utcnow()
    counts = {}
    for label, model, column, cutoff in (
        ("rate_limits", RateLimit, RateLimit.window_start, now - timedelta(days=1)),
        ("sessions", Session, Session.last_seen, now - timedelta(days=1)),
        ("reset_tokens", PasswordResetToken, PasswordResetToken.created_at, now - timedelta(days=7)),
        ("login_attempts", LoginAttempt, LoginAttempt.created_at, now - timedelta(days=90)),
    ):
        condition = column < cutoff
        if model is Session:
            condition = (Session.revoked.is_(True) & condition) | (Session.absolute_expires < now)
        if model is PasswordResetToken:
            condition = ((PasswordResetToken.status != "pending") & condition) | (PasswordResetToken.expires_at < now)
        result = await db.execute(delete(model).where(condition))
        counts[label] = result.rowcount or 0
    # An uploaded attachment becomes referenced by exactly one chat message or
    # sticker. Keep unreferenced uploads for a day so a slow client can finish.
    used_by_message = select(ChatMessage.id).where(ChatMessage.attachment_id == Attachment.id)
    used_by_sticker = select(Sticker.id).where(Sticker.attachment_id == Attachment.id)
    orphan = (await db.execute(select(Attachment).where(~used_by_message.exists(),
                ~used_by_sticker.exists(), Attachment.created_at < now - timedelta(days=1)))).scalars().all()
    from app.core import files
    for row in orphan:
        files.delete(row.file_path)
        await db.delete(row)
    counts["attachments"] = len(orphan)
    keep = (await db.execute(select(PluginSetting).join(Plugin, Plugin.id == PluginSetting.plugin_id)
              .where(Plugin.component == "tool_backup", PluginSetting.name == "keep_days"))).scalar_one_or_none()
    days = int(keep.value) if keep and keep.value.isdigit() else 30
    counts.update(await backups.cleanup(db, max(1, min(days, 365))))
    return counts


async def _digest(db, actor_id):
    now = utcnow()
    day = now.date().isoformat()
    subscriptions = (await db.execute(select(ForumSubscription).join(User, User.id == ForumSubscription.user_id)
                      .join(DiscussionThread, DiscussionThread.id == ForumSubscription.thread_id)
                      .where(User.status == "active", DiscussionThread.deleted_at.is_(None)))).scalars().all()
    created = 0
    for sub in subscriptions:
        posts = (await db.execute(select(DiscussionPost.id, DiscussionPost.thread_id)
                  .where(DiscussionPost.thread_id == sub.thread_id, DiscussionPost.deleted_at.is_(None),
                         DiscussionPost.user_id != sub.user_id,
                         DiscussionPost.created_at >= now - timedelta(days=1)))).all()
        if not posts:
            continue
        exists = (await db.execute(select(DigestDelivery).where(
            DigestDelivery.user_id == sub.user_id, DigestDelivery.period_date == day))).scalar_one_or_none()
        if exists is None:
            exists = DigestDelivery(user_id=sub.user_id, period_date=day, payload_json={"threads": {}})
            db.add(exists)
        threads = dict(exists.payload_json.get("threads", {}))
        threads[str(sub.thread_id)] = len(posts)
        exists.payload_json = {"threads": threads, "posts": sum(threads.values())}
        created += 1
    await db.flush()
    return {"deliveries": created, "day": day}


async def _backup(db, actor_id):
    if config.DEMO_MODE:
        return {"skipped": "demo_mode"}
    row = (await db.execute(select(PluginSetting).join(Plugin, Plugin.id == PluginSetting.plugin_id)
              .where(Plugin.component == "tool_backup", PluginSetting.name == "include_uploads"))).scalar_one_or_none()
    include = bool(row and row.value == "1")
    artifact = await backups.create(db, actor_id=actor_id, include_uploads=include)
    keep = (await db.execute(select(PluginSetting).join(Plugin, Plugin.id == PluginSetting.plugin_id)
              .where(Plugin.component == "tool_backup", PluginSetting.name == "keep_days"))).scalar_one_or_none()
    days = int(keep.value) if keep and keep.value.isdigit() else 30
    removed = await backups.cleanup(db, max(1, min(days, 365)))
    return {"backup_id": artifact.id, "size": artifact.file_size, **removed}


HANDLERS = {"core.cleanup": _cleanup, "core.forum_digest": _digest,
            "core.friday_campaign": friday_campaign_task, "core.push_delivery": push_delivery_task,
            "tool_backup.task.run_backup": _backup}


async def _claim(db, task, *, manual=False):
    now = utcnow()
    token = secrets.token_hex(16)
    scheduled = next_run(task, now)
    condition = (ScheduledTask.id == task.id, ScheduledTask.enabled.is_(True),
                 or_(ScheduledTask.locked_until.is_(None), ScheduledTask.locked_until < now))
    if not manual:
        condition += (or_(ScheduledTask.next_run.is_(None), ScheduledTask.next_run <= now),)
    result = await db.execute(update(ScheduledTask).where(*condition).values(
        next_run=scheduled, lock_token=token, locked_until=now + timedelta(minutes=10)))
    if result.rowcount != 1:
        return None
    await db.commit()  # durable claim survives a handler rollback
    return token


async def execute(db, task: ScheduledTask, token: str, *, actor_id=None, manual=False) -> TaskRun:
    run = TaskRun(task_id=task.id, task_key=task.classname, status="running", triggered_by=actor_id)
    db.add(run)
    await db.commit()  # running history survives failures/crashes
    run_id, task_id, task_key = run.id, task.id, task.classname
    detail, error = {}, ""
    try:
        if task.plugin_id:
            plugin = (await db.execute(select(Plugin).where(Plugin.id == task.plugin_id))).scalar_one_or_none()
            enabled_flag = (await db.execute(select(PluginSetting).where(
                PluginSetting.plugin_id == task.plugin_id, PluginSetting.name == "enabled"))).scalar_one_or_none()
            if plugin is None or plugin.status != "enabled" or (enabled_flag and enabled_flag.value != "1"):
                run.status, detail = "skipped", {"reason": "plugin_disabled"}
                raise _SkipTask
        handler = HANDLERS.get(task.classname)
        if handler is None:
            run.status, error = "failed", "cron.unknown_task"
        else:
            detail = await handler(db, actor_id)
            run.status = "success"
    except _SkipTask:
        pass
    except Exception as exc:
        await db.rollback()
        # Never lazy-load an expired ORM object after rollback: that can attempt
        # synchronous IO inside AsyncSession. Re-select using captured scalars.
        run = (await db.execute(select(TaskRun).where(TaskRun.id == run_id))).scalar_one()
        run.status = "failed"
        error = str(getattr(exc, "detail", "cron.task_failed"))[:120]
        import logging
        logging.getLogger("tt.cron").error("task %s failed (%s), run=%s", task_key, type(exc).__name__, run_id)
    run.detail_json, run.error_key, run.finished_at = detail, error, utcnow()
    await db.execute(update(ScheduledTask).where(ScheduledTask.id == task_id,
                     ScheduledTask.lock_token == token).values(lock_token="", locked_until=None, last_run=run.finished_at))
    await audit(db, action="task.finished", actor_id=actor_id, entity_type="scheduled_task",
                entity_id=task_key, after={"status": run.status, "manual": manual, "detail": detail},
                severity="warning" if run.status == "failed" else "info")
    await db.commit()
    await bus.dispatch("task.finished", {"task": task_key, "status": run.status, "run_id": run.id})
    return run


async def run_due(db, *, actor_id=None) -> list[TaskRun]:
    now = utcnow()
    tasks = (await db.execute(select(ScheduledTask).where(ScheduledTask.enabled.is_(True),
              or_(ScheduledTask.next_run.is_(None), ScheduledTask.next_run <= now),
              or_(ScheduledTask.locked_until.is_(None), ScheduledTask.locked_until < now))
              .order_by(ScheduledTask.id).limit(20))).scalars().all()
    runs = []
    for task in tasks:
        token = await _claim(db, task)
        if token:
            runs.append(await execute(db, task, token, actor_id=actor_id))
    return runs


async def run_now(db, task_id: int, *, actor_id=None) -> TaskRun:
    task = (await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_id))).scalar_one_or_none()
    if task is None:
        from fastapi import HTTPException
        raise HTTPException(404, "cron.task_not_found")
    if not task.enabled:
        from fastapi import HTTPException
        raise HTTPException(409, "cron.task_disabled")
    token = await _claim(db, task, manual=True)
    if token is None:
        from fastapi import HTTPException
        raise HTTPException(409, "cron.task_busy")
    return await execute(db, task, token, actor_id=actor_id, manual=True)
