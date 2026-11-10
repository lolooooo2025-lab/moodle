"""Netlify-specific end-to-end checks: chunked upload, signed Range download,
background backup/cron contracts and permission boundaries.

Requires the real Functions path on TT_BASE (default http://127.0.0.1:8000) and
TT_NETLIFY=1. Uses disposable fixtures and removes them afterwards.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import pathlib
import random
import sys
import time

import httpx

BASE = os.environ.get("TT_BASE", "http://127.0.0.1:8000")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD  # noqa: E402

RESULTS: list[tuple[str, bool]] = []
RUN = str(random.randint(100000, 999999))
SIZE = 16 * 1024 * 1024 + 123
CHUNK = 3 * 1024 * 1024
RANGE = 4 * 1024 * 1024


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return bool(ok)


def client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=120, follow_redirects=False,
                        headers={"User-Agent": "tt-verify-netlify/1.0"})


def login(c: httpx.Client, phone: str, password: str) -> dict:
    r = c.post("/api/auth/login", json={"phone": phone, "password": password}).json()
    if not r.get("success"):
        raise RuntimeError(f"login failed: {r}")
    return {"X-Sesskey": r["data"]["sesskey"], "Origin": BASE}


async def cleanup(lib_id: int, key: str) -> None:
    from sqlalchemy import delete
    from app.core.db import get_sessionmaker, dispose_db
    from app.core import objectstore
    from app import models as m
    try:
        async with get_sessionmaker()() as db:
            if lib_id:
                await db.execute(delete(m.UserLibrary).where(m.UserLibrary.library_item_id == lib_id))
                await db.execute(delete(m.LibraryItem).where(m.LibraryItem.id == lib_id))
            await db.execute(delete(m.RateLimit))
            await db.commit()
        if key:
            await objectstore.remove(key)
    finally:
        await dispose_db()


def main() -> int:
    print("== Taleb Talta Netlify transfer verification ==")
    owner = client()
    OH = login(owner, OWNER_PHONE, OWNER_PASSWORD)
    stu = client()
    phone = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    r = stu.post("/api/auth/register", json={"phone": phone, "password": STUDENT_PASSWORD,
                 "name": "طالب نتليفاي", "guardian_phone": "011" + "".join(str(random.randint(0, 9)) for _ in range(8)),
                 "division_id": 1, "website": "", "elapsed_ms": 5000}).json()
    check("fixture student registered", r.get("success"))
    SH = login(stu, phone, STUDENT_PASSWORD)

    data = b"a" * SIZE
    digest = hashlib.sha256(data).hexdigest()
    lib_id = 0
    key = ""
    try:
        body = {"filename": "netlify-large.txt", "size": SIZE, "sha256": digest}
        check("transfer create requires CSRF", owner.post("/api/transfers/uploads", json=body).status_code == 403)
        r = owner.post("/api/transfers/uploads", json=body, headers=OH).json()
        check("transfer created", r.get("success"), r.get("message", ""))
        tid = r["data"]["upload_id"]
        count = r["data"]["chunk_count"]
        check("chunk count bounded", count == (SIZE + CHUNK - 1) // CHUNK and r["data"]["chunk_size"] == CHUNK)

        first = data[:CHUNK]
        check("chunk upload requires CSRF", owner.put(f"/api/transfers/uploads/{tid}/chunks/0", content=first).status_code == 403)
        check("other user cannot upload chunk", stu.put(f"/api/transfers/uploads/{tid}/chunks/0", content=first, headers=SH).status_code == 404)
        for i in range(count):
            block = data[i * CHUNK:(i + 1) * CHUNK]
            resp = owner.put(f"/api/transfers/uploads/{tid}/chunks/{i}", content=block,
                             headers={**OH, "Content-Type": "application/octet-stream"})
            if not check(f"chunk {i} uploaded", resp.status_code == 200, str(resp.status_code)):
                break
        dup = owner.put(f"/api/transfers/uploads/{tid}/chunks/0", content=first,
                        headers={**OH, "Content-Type": "application/octet-stream"})
        check("duplicate chunk rejected", dup.status_code == 409, str(dup.status_code) + " " + dup.text[:80])
        check("other user cannot complete", stu.post(f"/api/transfers/uploads/{tid}/complete", json={}, headers=SH).status_code == 404)
        r = owner.post(f"/api/transfers/uploads/{tid}/complete", json={}, headers=OH).json()
        check("transfer completed", r.get("success") and r["data"]["sha256"] == digest)

        manifest = json.dumps({"magic": "tt-transfer-v1", "upload_id": tid}).encode()
        r = owner.post("/api/library/submit", data={"title": "zznetlify-" + RUN, "description": "", "category": ""},
                       files={"upload": ("netlify-large.txt", manifest, "application/json")}, headers=OH).json()
        check("manifest consumed by original upload API", r.get("success"), r.get("message", ""))
        lib_id = r.get("data", {}).get("id", 0)
        check("student cannot approve upload", stu.post(f"/api/library/{lib_id}/approve", json={}, headers=SH).status_code == 403)
        check("owner approves upload", owner.post(f"/api/library/{lib_id}/approve", json={}, headers=OH).json().get("success"))

        dl = owner.get(f"/api/library/{lib_id}/download")
        check("large download redirects to signed ticket", dl.status_code == 303 and "/api/files/content?ticket=" in dl.headers.get("location", ""))
        ticket_url = dl.headers["location"]
        ticket = ticket_url.split("ticket=", 1)[1]
        head = owner.head(ticket_url)
        check("HEAD reports object size", head.status_code == 200 and head.headers.get("content-length") == str(SIZE))
        meta = owner.get(ticket_url + "&meta=1").json()
        check("ticket metadata", meta.get("size") == SIZE and meta.get("chunk_size") == RANGE)
        whole = owner.get(ticket_url)
        check("oversized unrange response refuses truncation", whole.status_code == 413)

        out = bytearray()
        start = 0
        ok = True
        while start < SIZE:
            resp = owner.get(ticket_url, headers={"Range": f"bytes={start}-"})
            if resp.status_code != 206:
                ok = False
                break
            block = resp.content
            expected = min(RANGE, SIZE - start)
            if len(block) != expected or resp.headers.get("content-range") != f"bytes {start}-{start + expected - 1}/{SIZE}":
                ok = False
                break
            out.extend(block)
            start += len(block)
        check("Range download reassembles exact bytes", ok and hashlib.sha256(bytes(out)).hexdigest() == digest)
        check("invalid Range rejected", owner.get(ticket_url, headers={"Range": "bytes=-0"}).status_code == 416)
        check("out-of-bounds Range rejected", owner.get(ticket_url, headers={"Range": f"bytes={SIZE + 1}-"}).status_code == 416)
        check("tampered ticket rejected", owner.get("/api/files/content?ticket=" + ticket[:-4] + "0000").status_code == 403)

        # Background worker contract: backup rows first, then cron (the cron
        # worker may trigger its own backup task which would race with ours).
        token = os.environ.get("TT_CRON_TOKEN", "")
        check("internal cron rejects missing token", owner.post("/api/internal/cron/run", json={}).status_code == 403)
        r = owner.post("/api/admin/backups", json={"include_uploads": False}, headers=OH).json()
        check("backup scheduled", r.get("success"))
        bid = r.get("data", {}).get("id", 0)
        # backups.create auto-schedules the worker-background function; poll for it.
        row = {}
        for attempt in range(3):
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    rows = owner.get("/api/admin/backups").json()["data"]
                except Exception:
                    time.sleep(2)
                    continue
                row = next((x for x in rows if x["id"] == bid), {})
                if row.get("status") in ("ready", "failed"):
                    break
                time.sleep(1)
            if row.get("status") == "ready":
                break
            r = owner.post("/api/admin/backups", json={"include_uploads": False}, headers=OH).json()
            if not r.get("success"):
                break
            bid = r.get("data", {}).get("id", 0)
        check("background backup ready", row.get("status") == "ready" and len(row.get("sha256", "")) == 64)
        if row.get("status") == "ready":
            d = owner.get(f"/api/admin/backups/{bid}/download", follow_redirects=True, timeout=300)
            check("backup download checksum", d.status_code == 200 and hashlib.sha256(d.content).hexdigest() == row["sha256"])
            check("student cannot download backup", stu.get(f"/api/admin/backups/{bid}/download").status_code == 403)
            owner.delete(f"/api/admin/backups/{bid}", headers=OH)

        # Cron worker after the backup check (avoids the backup race).
        wr = owner.post("/.netlify/functions/worker-background", json={"kind": "cron"}, headers={"X-Internal-Token": token})
        check("background cron accepted", wr.status_code in (200, 202))

        # Discover the stored key for cleanup without exposing it through the API.
        async def find_key():
            from sqlalchemy import select
            from app.core.db import get_sessionmaker, dispose_db
            from app import models as m
            async with get_sessionmaker()() as db:
                row = (await db.execute(select(m.LibraryItem).where(m.LibraryItem.id == lib_id))).scalar_one_or_none()
                value = row.file_path if row else ""
            await dispose_db()
            return value
        key = asyncio.run(find_key())
    finally:
        asyncio.run(cleanup(lib_id, key))

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== RESULT: {passed}/{len(RESULTS)} checks passed ==")
    if passed != len(RESULTS):
        print("FAILED:", [n for n, ok in RESULTS if not ok])
        return 1
    print("ALL NETLIFY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
