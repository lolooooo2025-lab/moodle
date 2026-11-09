"""Event bus + plugin observers.

Moodle pattern: core\event\base::trigger() → manager::dispatch() → observers
registered in db/events.php. Here: a typed event name + payload dict, observers
registered by plugins at install time (plugin_events table) and dispatched
in-process. Side effects (audit, notifications) hang off events, not off the
request handler, so features stay decoupled.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Callable, Awaitable

Observer = Callable[[dict], Awaitable[None]]

class EventBus:
    def __init__(self):
        self._observers: dict[str, list[Observer]] = defaultdict(list)

    def subscribe(self, event: str, observer: Observer):
        self._observers[event].append(observer)

    def clear(self):
        self._observers.clear()

    async def dispatch(self, event: str, payload: dict):
        for obs in list(self._observers.get(event, [])):
            try:
                await obs(payload)
            except Exception:      # an observer must never break the request
                import logging
                logging.getLogger("tt.events").exception("observer failed for %s", event)

bus = EventBus()

# Canonical core events (plugins may observe these).
EVENTS = [
    "user.registered", "user.logged_in", "user.login_failed", "user.logged_out",
    "user.banned", "user.password_changed", "user.unbanned", "session.hijack_detected",
    "plugin.settings_updated", "plugin.installed", "plugin.uninstalled", "plugin.upgraded", "plugin.enabled",
    "plugin.disabled", "capability.denied", "course.created", "course.deleted",
    "exam.submitted", "message.sent", "forum.thread_created", "forum.post_created",
    "customization.updated", "settings.updated", "admin.user_updated", "admin.division_created", "admin.division_updated", "task.finished", "task.updated", "backup.created", "backup.downloaded", "backup.deleted", "report.exported",
    "moderation.warning", "moderation.banned", "moderation.reported", "purchase.confirmed", "broadcast.sent",
]
