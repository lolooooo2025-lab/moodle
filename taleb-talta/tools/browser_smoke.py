"""Headless-browser smoke test — drives the real UI in Chromium (Wave 0–4).

Captures screenshots into docs/screenshots/ and asserts: RTL layout, Cairo
computed font, LIGHT theme (no dark mode), zero console errors / failed requests,
and the Wave-1/2/3/4 flows (courses, library, exams, forum, chat, moderation).
"""
import os, sys, random, pathlib, asyncio
os.environ["LD_LIBRARY_PATH"] = "/tmp/chromium-libs/lib"
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.test_credentials import OWNER_PHONE, OWNER_PASSWORD, STUDENT_PASSWORD

BASE = "http://127.0.0.1:8000"
SHOTS = ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
RESULTS = []

def check(name, ok, detail=""):
    RESULTS.append((name, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def clear_rate_limits():
    try:
        from sqlalchemy import text
        from app.core.db import get_sessionmaker, dispose_db
        async def m():
            async with get_sessionmaker()() as s:
                await s.execute(text("DELETE FROM rate_limits")); await s.commit()
            await dispose_db()
        asyncio.run(m())
    except Exception:
        pass


def cleanup_browser(forum_title, phone="", field_machine="", theme_name="", menu_label="", backup_ids=()):
    try:
        from sqlalchemy import select, delete
        from app.core.db import get_sessionmaker, dispose_db
        from app import models as m, config
        async def m():
            async with get_sessionmaker()() as db:
                tids = list((await db.execute(select(m.DiscussionThread.id).where(
                    m.DiscussionThread.title == forum_title))).scalars().all())
                rids = list((await db.execute(select(m.ContentReport.id).where(
                    m.ContentReport.reason == "بلاغ تجريبي من المتصفح"))).scalars().all())
                if rids:
                    await db.execute(delete(m.ModerationAction).where(m.ModerationAction.report_id.in_(rids)))
                    await db.execute(delete(m.ContentReport).where(m.ContentReport.id.in_(rids)))
                if tids:
                    await db.execute(delete(m.ForumSubscription).where(m.ForumSubscription.thread_id.in_(tids)))
                    await db.execute(delete(m.DiscussionPost).where(m.DiscussionPost.thread_id.in_(tids)))
                    await db.execute(delete(m.DiscussionThread).where(m.DiscussionThread.id.in_(tids)))
                await db.execute(delete(m.ChatMessage).where(m.ChatMessage.body == "رسالة متصفح في قناة الشعبة"))
                if field_machine:
                    fids = list((await db.execute(select(m.CustomField.id).where(m.CustomField.machine_name == field_machine))).scalars().all())
                    if fids:
                        await db.execute(delete(m.CustomFieldValue).where(m.CustomFieldValue.field_id.in_(fids)))
                        await db.execute(delete(m.CustomField).where(m.CustomField.id.in_(fids)))
                if theme_name:
                    presets = (await db.execute(select(m.ThemePreset).where(m.ThemePreset.name == theme_name))).scalars().all()
                    keys = [f"preset-{p.id}" for p in presets]
                    if keys:
                        await db.execute(delete(m.RoleTheme).where(m.RoleTheme.theme_key.in_(keys)))
                        await db.execute(delete(m.SiteSetting).where(m.SiteSetting.key == "site.theme", m.SiteSetting.value.in_(keys)))
                        await db.execute(delete(m.ThemePreset).where(m.ThemePreset.id.in_([p.id for p in presets])))
                if menu_label:
                    await db.execute(delete(m.MenuItem).where(m.MenuItem.label == menu_label))
                if phone:
                    uid = (await db.execute(select(m.User.id).where(m.User.phone == phone))).scalar_one_or_none()
                    if uid:
                        await db.execute(delete(m.DashboardPreference).where(m.DashboardPreference.user_id == uid))
                if backup_ids:
                    rows = (await db.execute(select(m.BackupArtifact).where(m.BackupArtifact.id.in_(list(backup_ids))))).scalars().all()
                    for row in rows:
                        (config.BACKUP_DIR / row.file_name).unlink(missing_ok=True)
                    await db.execute(delete(m.BackupArtifact).where(m.BackupArtifact.id.in_(list(backup_ids))))
                await db.commit()
            await dispose_db()
        asyncio.run(m())
    except Exception:
        pass


def main():
    clear_rate_limits()
    errors, failed = [], []
    field_machine = theme_name = menu_label = ""
    browser_backups = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/tmp/chromium-bin", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  locale="ar-EG", timezone_id="Africa/Cairo")
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(r.url))

        # 1. login page — RTL + Cairo + LIGHT theme
        page.goto(BASE + "/login", wait_until="networkidle")
        check("login page RTL", page.evaluate("document.documentElement.dir") == "rtl")
        font = page.evaluate("getComputedStyle(document.body).fontFamily")
        check("Cairo is the computed font", "Cairo" in font, font)
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        check("default theme is light (no dark mode)", theme == "light", theme)
        bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
        check("background is light", bg in ("rgb(247, 248, 251)", "rgb(255, 255, 255)"), bg)
        page.screenshot(path=str(SHOTS / "01-login.png"), full_page=True)

        # 2. register a fresh student (division 1) through the UI
        page.goto(BASE + "/register", wait_until="networkidle")
        phone = "012" + "".join(str(random.randint(0, 9)) for _ in range(8))
        page.fill("#name", "أحمد محمود")
        page.fill("#phone", phone)
        page.fill("#guardian_phone", "010" + "".join(str(random.randint(0, 9)) for _ in range(8)))
        page.select_option("#division_id", "1")
        page.fill("#password", STUDENT_PASSWORD)
        page.wait_for_timeout(1800)
        page.click("#register-form button[type=submit]")
        page.wait_for_url("**/login", timeout=8000)
        check("register via UI lands on login", page.url.endswith("/login"))

        # 3. student login -> dashboard (light)
        page.fill("#phone", phone)
        page.fill("#password", STUDENT_PASSWORD)
        page.click("#login-form button[type=submit]")
        page.wait_for_url(BASE + "/", timeout=8000)
        page.wait_for_load_state("networkidle")
        check("student dashboard renders", "أحمد محمود" in page.content())
        page.screenshot(path=str(SHOTS / "03-student-dashboard.png"), full_page=True)

        # 4. theme switch among LIGHT variants only
        opts = page.eval_on_selector_all("#theme-select option", "els => els.map(e => e.value)")
        check("no dark theme offered", "navy" not in opts and set(opts) <= {"light", "neutral", "sky"}, str(opts))
        page.select_option("#theme-select", "sky")
        page.wait_for_timeout(200)
        check("sky theme applies", page.evaluate("document.documentElement.getAttribute('data-theme')") == "sky")
        page.select_option("#theme-select", "light")

        # 5. courses list — enrol in the demo course
        page.goto(BASE + "/courses", wait_until="networkidle")
        page.wait_for_selector(".course-card", timeout=8000)
        check("courses list renders", page.locator(".course-card").count() >= 1)
        page.screenshot(path=str(SHOTS / "11-courses-list.png"), full_page=True)
        enrol = page.locator("[data-enrol]").first
        enrolled_course_id = enrol.get_attribute("data-enrol") if enrol.count() else None
        if enrol.count():
            enrol.click()
            page.wait_for_timeout(900)
        if enrolled_course_id:
            page.goto(BASE + "/courses/" + enrolled_course_id, wait_until="networkidle")
        else:
            page.goto(BASE + "/courses", wait_until="networkidle")
            page.locator(".course-card a.btn").first.click()
            page.wait_for_load_state("networkidle")
        check("course detail renders sections", page.locator(".section-block").count() >= 1)
        page.screenshot(path=str(SHOTS / "12-course-detail.png"), full_page=True)

        # 6. lesson player — answer the question, watch progress
        page.locator(".lesson-row a.btn").first.click()
        page.wait_for_load_state("networkidle")
        check("lesson player renders items", page.locator(".player-item").count() >= 1)
        page.screenshot(path=str(SHOTS / "13-lesson-player.png"), full_page=True)
        qbtn = page.locator("[data-check]").first
        if qbtn.count():
            page.locator(".item-question input[type=radio]").first.check()
            qbtn.click()
            page.wait_for_timeout(600)
        check("question feedback shown", page.locator("[data-feedback]").first.inner_text() != "")

        # 7. library — shared list + save to private space
        page.goto(BASE + "/library", wait_until="networkidle")
        page.wait_for_selector(".lib-card", timeout=8000)
        check("library renders approved items", page.locator(".lib-card").count() >= 1)
        page.screenshot(path=str(SHOTS / "14-library.png"), full_page=True)
        save = page.locator("[data-save]").first
        if save.count():
            save.click(); page.wait_for_timeout(600)
        page.click("[data-tab=private]")
        page.wait_for_timeout(500)
        check("private space shows saved item", page.locator("#private-grid .lib-card").count() >= 1)
        page.screenshot(path=str(SHOTS / "15-private-space.png"), full_page=True)

        # 7b. exams — take the demo exam, submit, review
        page.on("dialog", lambda d: d.accept())
        page.goto(BASE + "/exams", wait_until="networkidle")
        page.wait_for_selector(".course-card", timeout=8000)
        check("exams list renders", page.locator(".course-card").count() >= 1)
        page.screenshot(path=str(SHOTS / "18-exams-list.png"), full_page=True)
        page.locator(".course-card a.btn").first.click()
        page.wait_for_load_state("networkidle")
        page.click("#start-btn")
        page.wait_for_selector(".exam-question", timeout=8000)
        check("exam runner renders questions", page.locator(".exam-question").count() >= 1)
        page.screenshot(path=str(SHOTS / "19-exam-runner.png"), full_page=True)
        page.locator(".exam-question input[type=radio]").first.check()
        page.click("#submit-btn")
        page.wait_for_selector("#exam-result:not([hidden])", timeout=8000)
        check("exam result shown", page.locator("#result-score").inner_text() != "")
        page.click("#review-link")
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(".review-item", timeout=8000)
        check("exam review renders items", page.locator(".review-item").count() >= 1)
        page.screenshot(path=str(SHOTS / "20-exam-review.png"), full_page=True)

        # 7c. Wave 3 — forum, thread reply, report, chat channel
        page.goto(BASE + "/forum", wait_until="networkidle")
        page.wait_for_selector(".thread-row", timeout=8000)
        check("forum index renders threads", page.locator(".thread-row").count() >= 1)
        check("forum disclaimer visible", "مسؤولية صاحبها" in page.content())
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "23-forum.png"), full_page=True)
        page.click("#new-thread-btn")
        forum_title = "مراجعة المتصفح " + str(random.randint(1000, 9999))
        page.fill("#thread-title", forum_title)
        page.fill("#thread-body", "سؤال تجريبي من المتصفح")
        page.click("#new-thread-form button[type=submit]")
        page.wait_for_url("**/forum/*", timeout=8000)
        page.wait_for_selector("#thread-posts .forum-post", timeout=8000)
        check("thread detail renders posts", page.locator("#thread-posts .forum-post").count() >= 1)
        page.fill("#reply-body", "رد تجريبي من المتصفح")
        page.click("#reply-form button[type=submit]")
        page.wait_for_timeout(800)
        check("reply appears in thread", page.locator("#thread-posts .forum-post").count() >= 2)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "24-thread.png"), full_page=True)
        # Report the seeded demo thread's first post (second row after our new thread).
        page.goto(BASE + "/forum", wait_until="networkidle")
        page.locator(".thread-row .thread-link").nth(1).click()
        page.wait_for_selector("[data-report]", timeout=8000)
        page.locator("[data-report]").first.click()
        page.wait_for_selector("#community-report-dialog", timeout=8000)
        page.fill("#community-report-reason", "بلاغ تجريبي من المتصفح")
        page.click("#community-report-form button[type=submit]")
        page.wait_for_timeout(800)
        check("report dialog submits", page.locator("#community-report-dialog").is_hidden())

        page.goto(BASE + "/chat", wait_until="networkidle")
        page.wait_for_selector("#conversation:not([hidden])", timeout=8000)
        check("chat channel list renders", page.locator(".channel-row").count() >= 1)
        page.fill("#message-body", "رسالة متصفح في قناة الشعبة")
        page.click("#send-btn")
        page.wait_for_selector(".message-bubble.mine", timeout=8000)
        check("chat message sent from UI", page.locator(".message-bubble.mine").count() >= 1)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "25-chat.png"), full_page=True)

        # 8. logout, owner login -> admin course + library management
        page.click("#logout-btn")
        page.wait_for_url("**/login", timeout=8000)
        page.fill("#phone", OWNER_PHONE)
        page.fill("#password", OWNER_PASSWORD)
        page.click("#login-form button[type=submit]")
        page.wait_for_url(BASE + "/", timeout=8000)
        page.goto(BASE + "/admin/courses", wait_until="networkidle")
        check("admin course management renders", page.locator("#course-form").count() == 1)
        page.screenshot(path=str(SHOTS / "16-admin-courses.png"), full_page=True)
        page.goto(BASE + "/admin/library", wait_until="networkidle")
        page.wait_for_timeout(500)
        check("admin moderation queue renders", "pending-list" in page.content())
        page.screenshot(path=str(SHOTS / "17-admin-library.png"), full_page=True)
        page.goto(BASE + "/admin/exams", wait_until="networkidle")
        page.wait_for_timeout(500)
        check("admin exam manager renders", page.locator("#question-form").count() == 1 and
              page.locator("#exam-form").count() == 1)
        page.screenshot(path=str(SHOTS / "21-admin-exams.png"), full_page=True)
        page.goto(BASE + "/admin/moderation", wait_until="networkidle")
        page.wait_for_selector("#report-list .report-card", timeout=8000)
        check("moderation queue renders report", page.locator("#report-list .report-card").count() >= 1)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "26-moderation.png"), full_page=True)
        page.locator("[data-decision=approve]").first.click()
        page.wait_for_timeout(800)
        check("moderation approve/dismiss works", page.locator("#report-list .report-card").count() == 0)
        page.click("[data-tab=dictionary]")
        page.wait_for_selector("#word-list .word-row", timeout=8000)
        check("profanity dictionary manager renders", page.locator("#word-list .word-row").count() >= 1)

        page.goto(BASE + "/courses/1/gradebook", wait_until="networkidle")
        page.wait_for_timeout(500)
        check("gradebook renders", page.locator("#gradebook-table").count() == 1)
        page.screenshot(path=str(SHOTS / "22-gradebook.png"), full_page=True)


        # ---- Wave 4: administration, builders, reports, tasks and backups ----
        suffix = str(random.randint(100000, 999999))
        field_machine = "browser_w4_" + suffix
        theme_name = "ثيم المتصفح " + suffix
        menu_label = "قائمة المتصفح " + suffix
        page.goto(BASE + "/admin/users", wait_until="networkidle")
        page.wait_for_selector("#users-body tr", timeout=8000)
        check("admin user manager renders rows", page.locator("#users-body tr").count() >= 1)
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "27-admin-users.png"), full_page=True)

        page.goto(BASE + "/admin/settings", wait_until="networkidle")
        page.wait_for_selector("#site-name", timeout=8000)
        check("settings tree has five sections", page.locator("[data-settings-tab]").count() == 5)
        page.click("[data-settings-tab=fields]")
        page.click("#add-field")
        page.fill("#field-label", "حقل المتصفح " + suffix)
        page.fill("#field-machine", field_machine)
        page.click("#field-form button[type=submit]")
        page.wait_for_selector(f"#fields-body code:has-text('{field_machine}')", timeout=8000)
        check("custom-field builder creates a field", page.locator(f"#fields-body code:has-text('{field_machine}')").count() == 1)
        page.click("[data-settings-tab=dashboard]")
        page.wait_for_selector("#default-block-list .builder-row", timeout=8000)
        check("role dashboard builder lists blocks", page.locator("#default-block-list .builder-row").count() >= 6)
        page.locator("#default-block-list .builder-row").first.locator("[data-default-move='1']").click()
        page.click("#save-default-blocks"); page.wait_for_timeout(500)
        order = page.evaluate("fetch('/api/admin/dashboard/defaults/student').then(r=>r.json()).then(j=>j.data.map(b=>b.key))")
        check("dashboard builder saves reordered defaults", order[0] != "courses", str(order[:2]))
        page.locator("#default-block-list .builder-row").nth(1).locator("[data-default-move='-1']").click()
        page.click("#save-default-blocks"); page.wait_for_timeout(400)
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "28-dashboard-builder.png"), full_page=True)

        page.click("[data-settings-tab=themes]")
        page.wait_for_selector("#theme-list .builder-row", timeout=8000)
        page.fill("#theme-name", theme_name)
        page.select_option("#theme-primary", "#113B77")
        page.click("#theme-form button[type=submit]")
        page.wait_for_selector(f"#theme-list .builder-row:has-text('{theme_name}')", timeout=8000)
        preset_row = page.locator("#theme-list .builder-row", has_text=theme_name)
        preset_row.locator("[data-activate-theme]").click(); page.wait_for_timeout(400)
        page.evaluate("document.cookie = 'tt_theme=; path=/; max-age=0'")
        page.reload(wait_until="networkidle")
        check("theme preset activates across reload", page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--primary').trim()") == "#113B77")
        page.click("[data-settings-tab=themes]")
        page.wait_for_selector(f"#theme-list .builder-row:has-text('{theme_name}')", timeout=8000)
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "29-theme-designer.png"), full_page=True)
        page.locator("#theme-list .builder-row", has_text="فاتح").locator("[data-activate-theme]").click(); page.wait_for_timeout(300)
        page.locator("#theme-list .builder-row", has_text=theme_name).locator("[data-delete-theme]").click(); page.wait_for_timeout(500)
        check("theme preset can be deleted after reverting", page.locator("#theme-list .builder-row", has_text=theme_name).count() == 0)
        page.click("[data-settings-tab=menus]")
        page.click("#add-menu")
        page.fill("#menu-label", menu_label); page.fill("#menu-url", "/courses")
        page.select_option("#menu-role", "student")
        page.click("#menu-form button[type=submit]")
        page.wait_for_selector(f"#menus-body tr:has-text('{menu_label}')", timeout=8000)
        check("menu builder creates a role-targeted item", page.locator(f"#menus-body tr:has-text('{menu_label}')").count() == 1)
        page.locator("#menus-body tr", has_text=menu_label).locator("[data-delete-menu]").click(); page.wait_for_timeout(500)
        check("menu builder deletes an item", page.locator("#menus-body tr", has_text=menu_label).count() == 0)

        page.goto(BASE + "/admin/security", wait_until="networkidle")
        page.wait_for_selector("#security-form input", timeout=8000)
        check("owner security policy renders bounded inputs", page.locator("#security-form input[type=number]").count() >= 7)
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "30-admin-security.png"), full_page=True)
        page.goto(BASE + "/admin/reports", wait_until="networkidle")
        page.wait_for_selector("#report-body tr", timeout=8000)
        page.select_option("#report-kind", "grades")
        page.click("#report-filters button[type=submit]")
        page.wait_for_timeout(700)
        check("report filters render grade rows", page.locator("#report-body tr").count() >= 1)
        with page.expect_download() as dl:
            page.click("#export-csv")
        dl.value.path()
        check("report CSV downloads from UI", dl.value.suggested_filename.endswith(".csv"))
        with page.expect_download() as dl:
            page.click("#export-xlsx")
        dl.value.path()
        check("report Excel downloads from UI", dl.value.suggested_filename.endswith(".xlsx"))
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "31-admin-reports.png"), full_page=True)

        page.goto(BASE + "/admin/tasks", wait_until="networkidle")
        page.wait_for_selector("#tasks-body tr", timeout=8000)
        check("cron manager lists scheduled tasks", page.locator("#tasks-body tr").count() >= 3)
        cleanup_row = page.locator("#tasks-body tr", has_text="core.cleanup")
        cleanup_row.locator("[data-run-task]").click()
        page.wait_for_selector("#runs-body tr", timeout=10000)
        check("manual task run appears in history", page.locator("#runs-body tr").count() >= 1)
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "32-admin-tasks.png"), full_page=True)
        page.goto(BASE + "/admin/backups", wait_until="networkidle")
        page.wait_for_selector("#backup-form", timeout=8000)
        page.click("#backup-form button[type=submit]")
        page.wait_for_selector("#backups-body [data-delete-backup]", timeout=15000)
        first_backup = page.locator("#backups-body tr").first
        browser_backups.append(int(first_backup.locator("[data-delete-backup]").get_attribute("data-delete-backup")))
        check("backup manager creates a ready artifact", "جاهزة" in first_backup.inner_text())
        with page.expect_download() as dl:
            first_backup.locator("a.btn").click()
        dl.value.path()
        check("backup artifact downloads from UI", dl.value.suggested_filename.endswith(".dump"))
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "33-admin-backups.png"), full_page=True)
        first_backup.locator("[data-delete-backup]").click(); page.wait_for_timeout(600)
        page.goto(BASE + "/admin/plugins", wait_until="networkidle")
        page.wait_for_selector("[data-plugin-settings=tool_backup]", timeout=8000)
        page.click("[data-plugin-settings=tool_backup]")
        page.wait_for_selector("#plugin-settings-fields input", timeout=8000)
        check("typed plugin settings dialog opens", page.locator("#plugin-settings-fields input").count() >= 2)
        page.click("#plugin-settings-form [data-close-dialog]")

        # Student-facing personalization created by the owner above.
        page.click("#logout-btn"); page.wait_for_url("**/login", timeout=8000)
        page.fill("#phone", phone); page.fill("#password", STUDENT_PASSWORD)
        page.click("#login-form button[type=submit]"); page.wait_for_url(BASE + "/", timeout=8000)
        page.wait_for_load_state("networkidle")
        page.click("#customize-dashboard")
        page.wait_for_selector("#dashboard-block-list .builder-row", timeout=8000)
        page.locator("#dashboard-block-list .builder-row").first.locator("[data-move='1']").click()
        page.click("#save-dashboard"); page.wait_for_timeout(1200); page.wait_for_load_state("networkidle")
        personal = page.evaluate("fetch('/api/dashboard').then(r=>r.json()).then(j=>j.data.map(b=>b.key))")
        check("student dashboard preference persists", personal[0] != "courses", str(personal[:2]))
        page.goto(BASE + "/profile", wait_until="networkidle")
        page.wait_for_selector(f"#profile-cf-{field_machine}", timeout=8000)
        page.fill(f"#profile-cf-{field_machine}", "قيمة تجريبية")
        page.click("#profile-form button[type=submit]"); page.wait_for_timeout(600)
        page.reload(wait_until="networkidle")
        check("profile custom value persists", page.input_value(f"#profile-cf-{field_machine}") == "قيمة تجريبية")
        page.evaluate("window.scrollTo(0, 0)"); page.wait_for_timeout(150)
        page.screenshot(path=str(SHOTS / "34-profile-custom-fields.png"), full_page=True)

        browser.close()
    cleanup_browser(forum_title, phone, field_machine, theme_name, menu_label, browser_backups)

    check("zero console errors", len(errors) == 0, "; ".join(errors[:3]))
    check("zero failed requests", len(failed) == 0, "; ".join(failed[:3]))
    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"\n== BROWSER SMOKE: {passed}/{len(RESULTS)} passed ==")
    sys.exit(0 if passed == len(RESULTS) else 1)

if __name__ == "__main__":
    main()
