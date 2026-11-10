"""Long-running cron worker. Run: python -m app.cron [--once].

Uses the same database schedule/locks/history as the HTTP cron endpoint. No
shell commands are built from user input; handlers are a fixed registry.
"""
from __future__ import annotations
import asyncio
import signal
import sys
from app.core.db import get_sessionmaker, dispose_db
from app.core import cron


async def main(once=False):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    async with get_sessionmaker()() as db:
        await cron.seed_tasks(db)
        await db.commit()
    try:
        while not stop.is_set():
            async with get_sessionmaker()() as db:
                runs = await cron.run_due(db)
                for run in runs:
                    print(f"{run.task_key}: {run.status} {run.detail_json}", flush=True)
            if once:
                break
            try:
                await asyncio.wait_for(stop.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
    finally:
        await dispose_db()


if __name__ == "__main__":
    asyncio.run(main(once="--once" in sys.argv))
