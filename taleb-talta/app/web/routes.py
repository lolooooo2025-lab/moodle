"""Server-rendered web pages (Jinja2, RTL, Egyptian Arabic).

Shares the core with the API: same session, capabilities, i18n, audit. The
layout is role-aware; every string comes from t(). A per-request CSP nonce is
provided by middleware for the small bootstrap inline script.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core.db import get_db
from app.core.i18n import t
from app.core.capabilities import tt_can
from app.api.deps import current_session
from app.models import (Division, MenuItem, Plugin, Course, CourseCategory,
                        CourseSection, Lesson, CourseStudent, LessonItem,
                        LessonProgress, LibraryItem, UserLibrary, User)
from sqlalchemy import func

templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))
router = APIRouter(tags=["web"])

# Core navigation per role (label_key, url, capability-or-None).
STUDENT_NAV = [
    ("nav.dashboard", "/", None),
    ("nav.courses", "/courses", None),
    ("nav.library", "/library", None),
    ("nav.exams", "/exams", None),
    ("nav.forum", "/forum", None),
    ("nav.messages", "/chat", None),
    ("nav.notifications", "/notifications", None),
    ("nav.live", "/live", None),
    ("buy.my_purchases", "/purchases", None),
    ("nav.profile", "/profile", "profile/edit"),
]
ADMIN_NAV = [
    ("nav.dashboard", "/admin", "report/view"),
    ("admin.courses", "/admin/courses", "course/edit"),
    ("admin.library", "/admin/library", "library/moderate"),
    ("admin.exams", "/admin/exams", "exam/create"),
    ("nav.forum", "/forum", None),
    ("nav.messages", "/chat", None),
    ("nav.moderation", "/admin/moderation", "moderation/review"),
    ("admin.users", "/admin/users", "user/manage"),
    ("admin.plugins", "/admin/plugins", "plugin/manage"),
    ("admin.audit", "/admin/audit", "audit/view"),
    ("admin.reports", "/admin/reports", "report/view"),
    ("admin.tasks", "/admin/tasks", "task/manage"),
    ("admin.settings", "/admin/settings", "site/settings"),
    ("admin.purchases", "/admin/purchases", "purchase/confirm"),
    ("admin.broadcasts", "/admin/broadcasts", "broadcast/send"),
    ("admin.campaigns", "/admin/campaigns", "campaign/manage"),
    ("admin.live", "/admin/live", "stream/manage"),
]

async def _ctx(request: Request, db: AsyncSession, **extra) -> dict:
    from app.core import customization, settings as site_settings
    sess, user, err = await current_session(request, db)
    nav = []
    if user:
        items = ADMIN_NAV if user.role in ("owner", "admin", "moderator") else STUDENT_NAV
        for label, url, cap in items:
            if cap is None or await tt_can(db, user, cap):
                nav.append({"label": t(label), "url": url})
        prows = (await db.execute(select(MenuItem).where(
            MenuItem.enabled == True, MenuItem.role.in_(["", user.role])  # noqa: E712
        ).order_by(MenuItem.sort_order, MenuItem.id))).scalars().all()
        for m in prows:
            nav.append({"label": m.label or t(m.label_key), "url": m.url})
    presets = await customization.theme_keys(db)
    theme = await customization.active_theme(db, user)
    cookie_theme = request.cookies.get("tt_theme")
    if cookie_theme and (cookie_theme in config.THEMES or cookie_theme in presets):
        theme = cookie_theme
    if theme not in config.THEMES and theme not in presets:
        theme = config.DEFAULT_THEME
    preset = presets.get(theme)
    ctx = {
        "request": request, "t": t, "user": user, "nav": nav, "theme": theme,
        "density": preset["density"] if preset else "comfortable",
        "sesskey": sess.sesskey if sess else "", "nonce": getattr(request.state, "csp_nonce", ""),
        "site_name": await site_settings.raw(db, "site.name") or t("app.name"),
        "demo_mode": config.DEMO_MODE,
        "logo_url": "/branding/logo",
        "themes": [{"key": k, "label": t("theme." + k)} for k in config.THEMES]
                  + [{"key": k, "label": v["name"]} for k, v in presets.items()],
    }
    ctx.update(extra)
    return ctx

def render(request, db, template, **extra):
    return _ctx(request, db, **extra)

async def _course_progress(db, user_id, course_id) -> int:
    lessons = (await db.execute(select(Lesson.id).join(
        CourseSection, Lesson.section_id == CourseSection.id).where(
        CourseSection.course_id == course_id, Lesson.deleted_at.is_(None)))).scalars().all()
    if not lessons:
        return 0
    done = 0
    for lid in lessons:
        total = (await db.execute(select(func.count(LessonItem.id)).where(
            LessonItem.lesson_id == lid))).scalar_one()
        if total == 0:
            p = (await db.execute(select(func.count(LessonProgress.id)).where(
                LessonProgress.user_id == user_id, LessonProgress.lesson_id == lid,
                LessonProgress.item_id.is_(None)))).scalar_one()
            if p:
                done += 1
        else:
            p = (await db.execute(select(func.count(LessonProgress.id)).where(
                LessonProgress.user_id == user_id, LessonProgress.lesson_id == lid,
                LessonProgress.item_id.is_not(None)))).scalar_one()
            if p >= total:
                done += 1
    return int(round(100 * done / len(lessons)))

async def _my_courses(db, user) -> list[dict]:
    rows = (await db.execute(select(Course).join(
        CourseStudent, CourseStudent.course_id == Course.id).where(
        CourseStudent.user_id == user.id, Course.deleted_at.is_(None)).order_by(
        CourseStudent.enrolled_at.desc()).limit(6))).scalars().all()
    cats = {c.id: c.name for c in (await db.execute(select(CourseCategory))).scalars().all()}
    divs = {d.id: d.name for d in (await db.execute(select(Division))).scalars().all()}
    out = []
    for c in rows:
        out.append({"id": c.id, "title": c.title,
                    "category_name": cats.get(c.category_id, ""),
                    "division_name": divs.get(c.division_id, ""),
                    "progress": await _course_progress(db, user.id, c.id)})
    return out

@router.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    from app.core import customization
    from app.models import DigestDelivery
    blocks = [b for b in await customization.dashboard(db, user) if b["enabled"]]
    digests = (await db.execute(select(DigestDelivery).where(DigestDelivery.user_id == user.id)
                .order_by(DigestDelivery.created_at.desc()).limit(3))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("nav.dashboard"),
                     my_courses=await _my_courses(db, user), blocks=blocks, digests=digests)
    return templates.TemplateResponse(request, "dashboard.html", ctx)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await _ctx(request, db, page_title=t("auth.login_title"))
    return templates.TemplateResponse(request, "auth/login.html", ctx)

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    divisions = (await db.execute(select(Division).order_by(Division.name))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("auth.register_title"), divisions=divisions)
    return templates.TemplateResponse(request, "auth/register.html", ctx)

@router.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await _ctx(request, db, page_title=t("auth.reset_title"))
    return templates.TemplateResponse(request, "auth/forgot.html", ctx)

@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await _ctx(request, db, page_title=t("auth.reset_title"))
    return templates.TemplateResponse(request, "auth/reset.html", ctx)

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("profile.profile"))
    return templates.TemplateResponse(request, "profile.html", ctx)

@router.get("/admin", response_class=HTMLResponse)
async def admin_home(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or user.role not in ("owner", "admin", "moderator"):
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("admin.dashboard"))
    return templates.TemplateResponse(request, "admin/dashboard.html", ctx)

@router.get("/admin/plugins", response_class=HTMLResponse)
async def admin_plugins(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "plugin/manage"):
        return RedirectResponse("/login", status_code=303)
    from app.core import plugins as engine
    await engine.sync_present(db)
    await db.commit()
    rows = (await db.execute(select(Plugin).order_by(Plugin.type, Plugin.name))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("admin.plugins"), plugins=rows)
    return templates.TemplateResponse(request, "admin/plugins.html", ctx)

# ---- Wave 5: purchases, broadcasts, campaigns, live -----------------------
@router.get("/admin/purchases", response_class=HTMLResponse)
async def admin_purchases_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "purchase/confirm", "admin/purchases.html", "admin.purchases")

@router.get("/admin/broadcasts", response_class=HTMLResponse)
async def admin_broadcasts_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "broadcast/send", "admin/broadcasts.html", "admin.broadcasts")

@router.get("/admin/campaigns", response_class=HTMLResponse)
async def admin_campaigns_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "campaign/manage", "admin/campaigns.html", "admin.campaigns")

@router.get("/admin/live", response_class=HTMLResponse)
async def admin_live_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "stream/manage", "admin/live.html", "admin.live")

@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "audit/view"):
        return RedirectResponse("/login", status_code=303)
    from app.models import AuditLog
    rows = (await db.execute(select(AuditLog).order_by(
        AuditLog.created_at.desc()).limit(100))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("admin.audit"), entries=rows)
    return templates.TemplateResponse(request, "admin/audit.html", ctx)

# ---- Wave 4: administration ------------------------------------------------
async def _admin_page(request, db, cap, template, title_key, **extra):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, cap):
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t(title_key), **extra)
    return templates.TemplateResponse(request, template, ctx)

@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, db: AsyncSession = Depends(get_db)):
    divisions = (await db.execute(select(Division).order_by(Division.name))).scalars().all()
    return await _admin_page(request, db, "user/manage", "admin/users.html", "admin.users", divisions=divisions)

@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "site/settings", "admin/settings.html", "admin.settings")

@router.get("/admin/security", response_class=HTMLResponse)
async def admin_security_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "site/security", "admin/security.html", "admin.security")

@router.get("/admin/reports", response_class=HTMLResponse)
async def admin_reports_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "report/view", "admin/reports.html", "admin.reports")

@router.get("/admin/tasks", response_class=HTMLResponse)
async def admin_tasks_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "task/manage", "admin/tasks.html", "admin.tasks")

@router.get("/admin/backups", response_class=HTMLResponse)
async def admin_backups_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _admin_page(request, db, "backup/manage", "admin/backups.html", "backup.title")

# ---- Wave 1: courses, lesson player, library -------------------------------
@router.get("/courses", response_class=HTMLResponse)
async def courses_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    from app.core.capabilities import tt_can
    can_create = await tt_can(db, user, "course/create")
    ctx = await _ctx(request, db, page_title=t("nav.courses"), can_create=can_create)
    return templates.TemplateResponse(request, "courses/list.html", ctx)

@router.get("/courses/{course_id}", response_class=HTMLResponse)
async def course_detail_page(course_id: int, request: Request,
                             db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("course.course"), course_id=course_id)
    return templates.TemplateResponse(request, "courses/detail.html", ctx)

@router.get("/learn/{lesson_id}", response_class=HTMLResponse)
async def learn_page(lesson_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("lesson.player_title"), lesson_id=lesson_id)
    return templates.TemplateResponse(request, "courses/learn.html", ctx)

@router.get("/library", response_class=HTMLResponse)
async def library_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    from app.core.capabilities import tt_can
    can_moderate = await tt_can(db, user, "library/moderate")
    ctx = await _ctx(request, db, page_title=t("nav.library"), can_moderate=can_moderate)
    return templates.TemplateResponse(request, "library/index.html", ctx)

@router.get("/admin/courses", response_class=HTMLResponse)
async def admin_courses_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "course/edit"):
        return RedirectResponse("/login", status_code=303)
    courses = (await db.execute(select(Course).where(
        Course.deleted_at.is_(None)).order_by(Course.created_at.desc()))).scalars().all()
    cats = (await db.execute(select(CourseCategory).order_by(CourseCategory.name))).scalars().all()
    divs = (await db.execute(select(Division).order_by(Division.name))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("admin.course_management"),
                     courses=courses, categories=cats, divisions=divs)
    return templates.TemplateResponse(request, "admin/courses.html", ctx)

@router.get("/admin/library", response_class=HTMLResponse)
async def admin_library_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "library/moderate"):
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("admin.library_moderation"))
    return templates.TemplateResponse(request, "admin/library.html", ctx)

# ---- Wave 2: exams & grading ---------------------------------------------
@router.get("/exams", response_class=HTMLResponse)
async def exams_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    can_edit = await tt_can(db, user, "exam/create")
    ctx = await _ctx(request, db, page_title=t("nav.exams"), can_edit=can_edit)
    return templates.TemplateResponse(request, "exams/list.html", ctx)

@router.get("/exams/{exam_id}", response_class=HTMLResponse)
async def exam_take_page(exam_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("exam.exam"), exam_id=exam_id)
    return templates.TemplateResponse(request, "exams/take.html", ctx)

@router.get("/attempts/{attempt_id}/review", response_class=HTMLResponse)
async def attempt_review_page(attempt_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("exam.review"), attempt_id=attempt_id)
    return templates.TemplateResponse(request, "exams/review.html", ctx)

@router.get("/courses/{course_id}/gradebook", response_class=HTMLResponse)
async def gradebook_page(course_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "report/view"):
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("exam.gradebook"), course_id=course_id)
    return templates.TemplateResponse(request, "exams/gradebook.html", ctx)

@router.get("/admin/exams", response_class=HTMLResponse)
async def admin_exams_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "exam/create"):
        return RedirectResponse("/login", status_code=303)
    courses = (await db.execute(select(Course).where(
        Course.deleted_at.is_(None)).order_by(Course.created_at.desc()))).scalars().all()
    ctx = await _ctx(request, db, page_title=t("exam.manage"), courses=courses)
    return templates.TemplateResponse(request, "admin/exams.html", ctx)

async def _student_page(request, db, template, title_key, **extra):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t(title_key), **extra)
    return templates.TemplateResponse(request, template, ctx)

@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "notifications.html", "nav.notifications")

@router.get("/purchases", response_class=HTMLResponse)
async def purchases_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "purchases.html", "buy.my_purchases")

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "campaigns.html", "notif.friday_archive")

@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_page(campaign_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "campaign-detail.html", "notif.friday", campaign_id=campaign_id)

@router.get("/live", response_class=HTMLResponse)
async def live_page(request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "live/list.html", "nav.live")

@router.get("/live/{stream_id}", response_class=HTMLResponse)
async def live_player_page(stream_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    return await _student_page(request, db, "live/player.html", "live.watch", stream_id=stream_id)


# ---- Wave 3: communication -------------------------------------------------
@router.get("/forum", response_class=HTMLResponse)
async def forum_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("forum.title"),
                     can_post=await tt_can(db, user, "forum/post"),
                     can_manage_course=await tt_can(db, user, "course/create"))
    return templates.TemplateResponse(request, "community/forum.html", ctx)

@router.get("/forum/{thread_id}", response_class=HTMLResponse)
async def thread_page(thread_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("forum.title"), thread_id=thread_id,
                     user_id=user.id, can_moderate=await tt_can(db, user, "moderation/review"))
    return templates.TemplateResponse(request, "community/thread.html", ctx)

@router.get("/chat", response_class=HTMLResponse)
@router.get("/messages", response_class=HTMLResponse)
async def chat_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("chat.title"), user_id=user.id,
                     initial_channel=request.query_params.get("channel", ""))
    return templates.TemplateResponse(request, "community/chat.html", ctx)

@router.get("/admin/moderation", response_class=HTMLResponse)
async def moderation_page(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None or not await tt_can(db, user, "moderation/review"):
        return RedirectResponse("/login", status_code=303)
    ctx = await _ctx(request, db, page_title=t("moderation.title"),
                     can_ban=await tt_can(db, user, "user/ban"))
    return templates.TemplateResponse(request, "admin/moderation.html", ctx)
