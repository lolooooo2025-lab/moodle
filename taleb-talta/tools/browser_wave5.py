"""Headless-browser coverage for Wave 5 UI (manual money, notifications, live).

External HLS playback and OS push delivery are intentionally not exercised here;
the player page is checked in scheduled state and push logic is covered by the
API verifier with a local provider stub.
"""
import os, sys, random, pathlib, asyncio
from datetime import datetime, timedelta, timezone
os.environ["LD_LIBRARY_PATH"] = "/tmp/chromium-libs/lib"
import httpx
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD
BASE = "http://127.0.0.1:8000"
SHOTS = ROOT / "docs" / "screenshots"; SHOTS.mkdir(parents=True, exist_ok=True)
RESULTS = []
RUN = str(random.randint(100000, 999999))
MARK = "zzwave5-browser-" + RUN


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)


def shot(page, name):
    page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
    page.screenshot(path=str(SHOTS / name), full_page=True)


def api():
    return httpx.Client(base_url=BASE, timeout=60)


def owner_login(c):
    r = c.post("/api/auth/login", json={"phone": OWNER_PHONE, "password": OWNER_PASSWORD}).json()
    assert r.get("success"), r
    return {"X-Sesskey": r["data"]["sesskey"]}


def register(c):
    p = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    g = "011" + "".join(str(random.randint(0, 9)) for _ in range(8))
    r = c.post("/api/auth/register", json={"phone": p, "password": STUDENT_PASSWORD, "name": MARK + "-stu",
               "guardian_phone": g, "division_id": 1, "website": "", "elapsed_ms": 5000}).json()
    assert r["success"], r
    r = c.post("/api/auth/login", json={"phone": p, "password": STUDENT_PASSWORD}).json()
    return p, r["data"]["user_id"]


def db(fn):
    from app.core.db import get_sessionmaker, dispose_db
    import threading
    async def m():
        try:
            async with get_sessionmaker()() as s:
                out = await fn(s); await s.commit(); return out
        finally:
            await dispose_db()
    result = []
    t = threading.Thread(target=lambda: result.append(asyncio.run(m())))
    t.start(); t.join()
    return result[0]


def make_campaign_due(title):
    from sqlalchemy import update
    from app.models import Campaign, utcnow
    async def fn(s):
        await s.execute(update(Campaign).where(Campaign.title == title).values(publish_at=utcnow() - timedelta(minutes=1)))
    db(fn)


def login_ui(page, phone, password):
    page.goto(BASE + "/login", wait_until="networkidle")
    page.fill("#phone", phone); page.fill("#password", password)
    page.click("#login-form button[type=submit]")
    page.wait_for_url(BASE + "/", timeout=10000)
    page.wait_for_load_state("networkidle")


def main():
    errors, failed = [], []
    from sqlalchemy import text
    async def clear(s):
        await s.execute(text("DELETE FROM rate_limits"))
    db(clear)
    c = api(); OH = owner_login(c)
    phone, uid = register(api())
    course = c.post("/api/courses", json={"title": MARK + "-course", "summary": "browser paid course", "division_id": 1}, headers=OH).json()["data"]["id"]
    sec = c.post(f"/api/courses/{course}/sections", json={"title": "unit"}, headers=OH).json()["data"]["id"]
    lesson = c.post(f"/api/sections/{sec}/lessons", json={"title": MARK + "-lesson"}, headers=OH).json()["data"]["id"]
    c.post(f"/api/lessons/{lesson}/items", data={"item_type": "text", "title": "content", "body": "paid content"}, headers=OH)
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    stream = c.post("/api/admin/streams", json={"title": MARK + "-stream", "description": "browser stream", "audience": "all",
                     "scheduled_at": future, "playback_url": "https://cdn.example.com/browser.m3u8",
                     "ingest_url": "rtmps://ingest.example.com/live", "publish_key": "browser-key-" + RUN}, headers=OH).json()["data"]["id"]
    today = datetime.now(timezone.utc).date()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    camp_title = MARK + "-friday"
    camp = c.post("/api/admin/campaigns", json={"week_date": friday.isoformat(), "title": camp_title, "body": "Friday message " + RUN}, headers=OH).json()["data"]["id"]
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path="/tmp/chromium-bin", args=["--no-sandbox", "--disable-dev-shm-usage"])
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="ar-EG")
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url))
            login_ui(page, OWNER_PHONE, OWNER_PASSWORD)
            check("RTL document", page.evaluate("document.documentElement.dir") == "rtl")

            # Owner prices the course through the real dialog.
            page.goto(BASE + f"/courses/{course}", wait_until="networkidle")
            page.wait_for_selector("#price-course", timeout=8000)
            page.click("#price-course"); page.wait_for_selector("#price-dialog[open]", timeout=5000)
            page.fill("#price-input", "150.00"); page.click("#price-form button[type=submit]")
            page.wait_for_selector("#course-actions .chip", timeout=8000)
            # A UI login deliberately revokes earlier sessions. Read back through
            # the browser's current session, not the now-revoked fixture client.
            price_now = page.evaluate("fetch('/api/courses/' + %d + '/detail').then(r => r.json()).then(j => j.data.price_cents)" % course)
            check("owner sets price from UI", price_now == 15000)
            shot(page, "35-course-pricing.png")

            # Live management + owner-only key reveal.
            page.goto(BASE + "/admin/live", wait_until="networkidle")
            page.wait_for_selector("#streams-body tr", timeout=8000)
            row = page.locator("#streams-body tr", has_text=MARK + "-stream")
            check("admin live table lists stream", row.count() == 1)
            row.locator("[data-key]").click(); page.wait_for_selector("#key-dialog[open]", timeout=5000)
            page.click("#reveal-key"); page.wait_for_timeout(500)
            check("owner reveals publish key in UI", page.input_value("#key-value") == "browser-key-" + RUN)
            check("owner reveals ingest URL in UI", page.input_value("#key-ingest") == "rtmps://ingest.example.com/live")
            shot(page, "36-admin-live-key.png")
            page.click("#key-dialog [data-close-dialog]")

            # Targeted broadcast to the individual student.
            page.goto(BASE + "/admin/broadcasts", wait_until="networkidle")
            page.select_option("#bc-audience", "user")
            page.fill("#bc-user-search", phone); page.wait_for_timeout(700)
            page.select_option("#bc-user", str(uid))
            page.fill("#bc-title", MARK + "-hello"); page.fill("#bc-body", "hello from browser")
            page.click("#broadcast-form button[type=submit]")
            page.wait_for_selector("#broadcast-history tr", timeout=8000)
            check("broadcast history shows sent notification", page.locator("#broadcast-history tr", has_text=MARK + "-hello").count() >= 1)
            shot(page, "37-admin-broadcasts.png")

            # Friday campaign schedule + publish.
            page.goto(BASE + "/admin/campaigns", wait_until="networkidle")
            page.wait_for_selector("#campaigns-body tr", timeout=8000)
            check("campaign scheduled in UI", page.locator("#campaigns-body tr", has_text=camp_title).count() == 1)
            shot(page, "38-admin-campaigns.png")
            make_campaign_due(camp_title)
            page.reload(wait_until="networkidle")
            page.locator("#campaigns-body tr", has_text=camp_title).locator("[data-publish]").click()
            page.wait_for_timeout(800)
            check("campaign published from UI", "published" in page.locator("#campaigns-body tr", has_text=camp_title).inner_text() or page.locator("#campaigns-body tr", has_text=camp_title).locator("a.btn").count() == 1)

            # Student requests purchase through the course dialog.
            page.click("#logout-btn"); page.wait_for_url("**/login", timeout=8000)
            login_ui(page, phone, STUDENT_PASSWORD)
            page.goto(BASE + f"/courses/{course}", wait_until="networkidle")
            page.wait_for_selector("#buy-course", timeout=8000)
            check("student sees locked paid course", page.locator("#sections .badge-pending").count() >= 1)
            page.click("#buy-course"); page.wait_for_selector("#purchase-dialog[open]", timeout=5000)
            page.fill("#purchase-reference", "BR-" + RUN); page.fill("#purchase-note", "browser transfer")
            page.click("#purchase-form button[type=submit]")
            page.wait_for_url("**/purchases", timeout=8000)
            page.wait_for_selector("#purchases-body tr", timeout=8000)
            check("student purchase request listed", page.locator("#purchases-body tr").count() >= 1)
            shot(page, "39-student-purchases.png")

            # Owner confirms from the review dialog.
            page.click("#logout-btn"); page.wait_for_url("**/login", timeout=8000)
            login_ui(page, OWNER_PHONE, OWNER_PASSWORD)
            page.goto(BASE + "/admin/purchases", wait_until="networkidle")
            page.wait_for_selector("#purchases-body [data-review]", timeout=8000)
            prow = page.locator("#purchases-body tr", has_text="BR-" + RUN)
            prow.locator("[data-review]").click(); page.wait_for_selector("#review-dialog[open]", timeout=5000)
            page.fill("#review-note", "verified in browser"); page.click("#confirm-purchase")
            page.wait_for_timeout(800)
            check("admin confirmation updates queue", page.locator("#purchases-body tr", has_text="BR-" + RUN).locator("[data-review]").count() == 0)
            shot(page, "40-admin-purchases.png")

            # Student inbox, read state, campaign archive and live player.
            page.click("#logout-btn"); page.wait_for_url("**/login", timeout=8000)
            login_ui(page, phone, STUDENT_PASSWORD)
            page.goto(BASE + "/notifications", wait_until="networkidle")
            page.wait_for_selector(".notification-card", timeout=8000)
            check("targeted notification visible", page.locator(".notification-card", has_text=MARK + "-hello").count() == 1)
            check("purchase notification visible", page.locator(".notification-card").count() >= 2)
            page.locator(".notification-card", has_text=MARK + "-hello").locator("[data-read]").click()
            page.wait_for_timeout(600)
            check("mark read removes unread button", page.locator(".notification-card", has_text=MARK + "-hello").locator("[data-read]").count() == 0)
            shot(page, "41-notifications.png")
            page.goto(BASE + "/campaigns", wait_until="networkidle")
            page.wait_for_selector("#campaign-list .card", timeout=8000)
            check("Friday archive identical body", page.locator("#campaign-list .card", has_text=camp_title).inner_text().find("Friday message " + RUN) >= 0)
            shot(page, "42-campaign-archive.png")
            page.goto(BASE + "/live", wait_until="networkidle")
            page.wait_for_selector("#live-list .card", timeout=8000)
            check("live list shows scheduled stream", page.locator("#live-list .card", has_text=MARK + "-stream").count() == 1)
            page.locator("#live-list .card", has_text=MARK + "-stream").locator("a.btn").click()
            page.wait_for_selector("#live-title", timeout=8000)
            check("player page renders stream metadata", page.inner_text("#live-title") == MARK + "-stream")
            check("scheduled player hides video", page.locator("#live-video").is_hidden())
            check("hls.js vendored locally", page.evaluate("typeof window.Hls") == "function")
            shot(page, "43-live-player.png")
            # Confirmed purchase now unlocks the lesson in the real player.
            page.goto(BASE + f"/learn/{lesson}", wait_until="networkidle")
            page.wait_for_selector(".player-item", timeout=8000)
            check("confirmed purchase unlocks lesson UI", page.locator(".player-item").count() >= 1)
            shot(page, "44-unlocked-lesson.png")
            browser.close()
        check("zero console errors", len(errors) == 0, "; ".join(errors[:3]))
        check("zero failed requests", len(failed) == 0, "; ".join(failed[:3]))
    finally:
        c.close()
        import verify_wave5
        asyncio.run(verify_wave5.cleanup([], [], [], []))
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== BROWSER WAVE5: {passed}/{len(RESULTS)} passed ==")
    sys.exit(0 if passed == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
