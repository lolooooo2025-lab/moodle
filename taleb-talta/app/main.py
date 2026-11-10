"""Taleb Talta — FastAPI application factory.

Security middleware sets CSP (per-request nonce, no unsafe-inline), HSTS,
nosniff, frame-options, referrer-policy, permissions-policy, and no-store on
private responses. Static assets are the only cacheable responses.
"""
from __future__ import annotations
import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from app import config
from app.core.db import init_db, get_sessionmaker, dispose_db, get_db
from app.core.i18n import t
from app.core import security
from app.core.capabilities import catalogue_defaults
from app.core import plugins as engine
from app.models import Division, User, RoleCapability, SiteSetting
from app.api import (auth as auth_api, plugins as plugins_api, users as users_api,
                     courses as courses_api, library as library_api, exams as exams_api,
                     forum as forum_api, chat as chat_api, moderation as moderation_api,
                     admin as admin_api, customization as customization_api,
                     reports as reports_api, tasks as tasks_api,
                     purchases as purchases_api, notifications as notifications_api, streams as streams_api)
from app.web import routes as web_routes

templates = Jinja2Templates(directory=str(config.APP_DIR / "templates"))

async def seed():
    """Idempotent seed: divisions, capability defaults, owner account.
    Seed data lives in database/seed.json (not hard-coded in code)."""
    import json, os
    seed_data = json.loads((config.BASE_DIR / "database" / "seed.json").read_text(encoding="utf-8"))
    async with get_sessionmaker()() as db:
        # divisions
        if (await db.execute(select(Division))).first() is None:
            for name in seed_data["divisions"]:
                db.add(Division(name=name))
        # capability defaults
        for role, cap, perm in catalogue_defaults():
            exists = (await db.execute(select(RoleCapability).where(
                RoleCapability.role == role, RoleCapability.capability == cap))).first()
            if exists is None:
                db.add(RoleCapability(role=role, capability=cap, permission=perm))
        # First owner bootstrap. The password must come from the environment or
        # private secrets file; no usable default password is shipped in source.
        if (await db.execute(select(User).where(User.role == "owner"))).first() is None:
            owner_pw = config.OWNER_PASSWORD
            if not owner_pw:
                raise RuntimeError("TT_OWNER_PASSWORD is required for first owner bootstrap")
            owner_phone = config.OWNER_PHONE
            if not owner_phone:
                raise RuntimeError("TT_OWNER_PHONE is required for first owner bootstrap")
            db.add(User(phone=owner_phone,
                        password_hash=security.hash_password(owner_pw),
                        name=seed_data["owner_name"],
                        guardian_phone=seed_data["owner_guardian_phone"],
                        role="owner", status="active"))
        await db.commit()
        # plugins: sync present + load enabled observers
        await engine.sync_present(db)
        await engine.load_enabled_observers(db)
        await db.commit()

async def seed_wave1():
    """Idempotent demo content: a course with lessons + library items (Wave 1).
    Content lives in database/seed_wave1.json; files are written to storage."""
    import json
    from app.models import (Course, CourseCategory, CourseSection, Lesson,
                            LessonItem, LibraryItem)
    from app.core import files
    path = config.BASE_DIR / "database" / "seed_wave1.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    async with get_sessionmaker()() as db:
        if (await db.execute(select(Course))).first() is not None:
            return                                   # already seeded
        owner = (await db.execute(select(User).where(User.role == "owner"))).scalar_one()
        divs = (await db.execute(select(Division).order_by(Division.id))).scalars().all()
        cat_ids = {}
        for name in data["categories"]:
            cat = (await db.execute(select(CourseCategory).where(
                CourseCategory.name == name))).scalar_one_or_none()
            if cat is None:
                cat = CourseCategory(name=name)
                db.add(cat)
                await db.flush()
            cat_ids[name] = cat.id
        cd = data["course"]
        course = Course(title=cd["title"], summary=cd["summary"],
                        category_id=cat_ids.get(cd["category"]),
                        division_id=divs[cd["division_index"]].id if divs else None,
                        visibility="visible", teacher_id=owner.id)
        db.add(course)
        await db.flush()
        for si, sec in enumerate(cd["sections"]):
            section = CourseSection(course_id=course.id, title=sec["title"], sort_order=si)
            db.add(section)
            await db.flush()
            for li, les in enumerate(sec["lessons"]):
                lesson = Lesson(section_id=section.id, title=les["title"], sort_order=li)
                db.add(lesson)
                await db.flush()
                for ii, item in enumerate(les["items"]):
                    it = LessonItem(lesson_id=lesson.id, item_type=item["type"],
                                    title=item.get("title", ""), body=item.get("body", ""),
                                    sort_order=ii)
                    if item["type"] == "question":
                        it.options_json = item["options"]
                        it.correct_index = item["correct"]
                    if item["type"] == "file":
                        saved = files.save("lessons", item["file_name"],
                                           item["file_content"].encode("utf-8"))
                        it.file_path, it.file_name = saved["key"], saved["file_name"]
                    db.add(it)
        for lib in data["library"]:
            saved = files.save("library", lib["file_name"], lib["file_content"].encode("utf-8"))
            db.add(LibraryItem(uploader_id=owner.id, title=lib["title"],
                               description=lib["description"], category=lib["category"],
                               file_path=saved["key"], file_name=saved["file_name"],
                               file_size=saved["file_size"], mime=saved["mime"],
                               status=lib["status"]))
        await db.commit()

async def seed_wave2():
    """Idempotent demo exam (Wave 2): a question bank + a timed exam on the demo course."""
    import json
    from app.models import Question, Exam, ExamQuestion, Course
    path = config.BASE_DIR / "database" / "seed_wave2.json"
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    async with get_sessionmaker()() as db:
        if (await db.execute(select(Exam))).first() is not None:
            return                                   # already seeded
        course = (await db.execute(select(Course).order_by(Course.id))).scalars().first()
        owner = (await db.execute(select(User).where(User.role == "owner"))).scalar_one()
        if course is None:
            return
        ed = data["exam"]
        exam = Exam(course_id=course.id, title=ed["title"], description=ed["description"],
                    time_limit_minutes=ed["time_limit_minutes"], max_attempts=ed["max_attempts"],
                    visibility="visible", created_by=owner.id)
        db.add(exam)
        await db.flush()
        for i, qd in enumerate(ed["questions"]):
            q = Question(course_id=course.id, qtype=qd["qtype"], prompt=qd["prompt"],
                         options_json=qd.get("options"), answer_json=qd.get("answer"),
                         explanation=qd.get("explanation", ""), created_by=owner.id)
            db.add(q)
            await db.flush()
            db.add(ExamQuestion(exam_id=exam.id, question_id=q.id, sort_order=i,
                                points=qd.get("points", 1)))
        await db.commit()

async def seed_wave3():
    """One-time communication defaults; never re-add words an admin disabled."""
    import json
    from app.models import SiteSetting, ProfanityWord, DiscussionThread, DiscussionPost, ForumSubscription
    from app.core.community import ensure_division_channels
    async with get_sessionmaker()() as db:
        marker = (await db.execute(select(SiteSetting).where(
            SiteSetting.key == "wave3.initialised"))).scalar_one_or_none()
        if marker:
            return
        words = json.loads((config.BASE_DIR / "database" / "profanity.json").read_text(encoding="utf-8"))
        from app.core.moderation import normalize
        for word in words["words"]:
            db.add(ProfanityWord(word=normalize(word), enabled=True))
        await ensure_division_channels(db)
        owner = (await db.execute(select(User).where(User.role == "owner"))).scalar_one()
        demo = json.loads((config.BASE_DIR / "database" / "seed_wave3.json").read_text(encoding="utf-8"))["forum"]
        thread = DiscussionThread(title=demo["title"], created_by=owner.id)
        db.add(thread)
        await db.flush()
        db.add(DiscussionPost(thread_id=thread.id, user_id=owner.id, body=demo["body"]))
        db.add(DiscussionPost(thread_id=thread.id, user_id=owner.id, body=demo["reply"]))
        db.add(ForumSubscription(thread_id=thread.id, user_id=owner.id))
        db.add(SiteSetting(key="wave3.initialised", value="1"))
        await db.commit()

async def seed_wave4():
    from app.core import customization, cron
    from app.models import MenuItem
    async with get_sessionmaker()() as db:
        await customization.seed_defaults(db)
        await cron.seed_tasks(db)
        # Repair the Wave-0 demo link now that the real backup screen exists.
        items = (await db.execute(select(MenuItem).where(MenuItem.url == "/admin/plugins/tool_backup"))).scalars().all()
        for item in items:
            item.url, item.icon = "/admin/backups", "download"
        await db.commit()

async def seed_wave5():
    from app.core import cron
    async with get_sessionmaker()() as db:
        await cron.seed_tasks(db)
        await db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed()
    await seed_wave1()
    await seed_wave2()
    await seed_wave3()
    await seed_wave4()
    await seed_wave5()
    yield
    await dispose_db()

def create_app() -> FastAPI:
    app = FastAPI(title=config.APP_NAME, lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def maintenance_gate(request: Request, call_next):
        from app.core import settings as site_settings
        from app.core.capabilities import tt_can
        from app.api.deps import current_session
        path = request.url.path
        exempt = (path.startswith(("/static/", "/api/auth/", "/branding/")) or path in
                  ("/healthz", "/login", "/register", "/forgot", "/reset", "/theme.css",
                   "/manifest.webmanifest", "/sw.js", "/favicon.ico"))
        if not exempt:
            async with get_sessionmaker()() as db:
                if await site_settings.boolean(db, "site.maintenance"):
                    sess, user, err = await current_session(request, db)
                    if user is None or not await tt_can(db, user, "site/settings"):
                        if path.startswith("/api/"):
                            return JSONResponse({"success": False, "message": t("site.maintenance"), "data": None}, status_code=503)
                        return templates.TemplateResponse(request, "maintenance.html",
                            {"request": request, "t": t, "site_name": await site_settings.raw(db, "site.name") or t("app.name")},
                            status_code=503)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce
        response = await call_next(request)
        # The live preview embeds the app in a cross-site iframe; allow that
        # only when TT_ALLOW_FRAMING=1 (dev/preview). Production keeps 'none'.
        allow_framing = config.ALLOW_FRAMING
        frame_ancestors = "*" if allow_framing else "'none'"
        csp = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{nonce}'; "
            "style-src 'self'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self' https:; "
            "media-src 'self' blob: https:; "
            "worker-src 'self' blob:; "
            "object-src 'none'; "
            f"frame-ancestors {frame_ancestors}; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not allow_framing:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if config.SESSION_COOKIE_SECURE:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # no-store on everything except static assets
        if not request.url.path.startswith("/static/") and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/static", StaticFiles(directory=str(config.APP_DIR / "static")), name="static")
    app.include_router(auth_api.router)
    app.include_router(plugins_api.router)
    app.include_router(users_api.router)
    app.include_router(courses_api.router)
    app.include_router(library_api.router)
    app.include_router(exams_api.router)
    app.include_router(forum_api.router)
    app.include_router(chat_api.router)
    app.include_router(moderation_api.router)
    app.include_router(admin_api.router)
    app.include_router(customization_api.router)
    app.include_router(reports_api.router)
    app.include_router(tasks_api.router)
    app.include_router(purchases_api.router)
    app.include_router(notifications_api.router)
    app.include_router(streams_api.router)
    app.include_router(web_routes.router)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/i18n.js")
    async def i18n_js():
        from fastapi.responses import Response
        import json
        from app.core.i18n import _load
        payload = "window.TT_STRINGS = " + json.dumps(_load("ar"), ensure_ascii=False) + ";"
        return Response(payload, media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/theme.css")
    async def theme_css(db: AsyncSession = Depends(get_db)):
        from fastapi.responses import Response
        from app.core import customization
        return Response(await customization.theme_css(db), media_type="text/css", headers={"Cache-Control": "no-cache"})

    @app.get("/branding/logo")
    async def branding_logo(db: AsyncSession = Depends(get_db)):
        from fastapi.responses import FileResponse
        from app.core import settings as site_settings, files
        key = await site_settings.raw(db, "site.logo_path")
        if key:
            try:
                path = files.resolve(key)
                return FileResponse(path, headers={"Cache-Control": "no-cache"})
            except files.FileError:
                pass
        return FileResponse(config.APP_DIR / "static" / "logo.png", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    async def manifest(db: AsyncSession = Depends(get_db)):
        from fastapi.responses import JSONResponse
        from app.core import settings as site_settings
        name = await site_settings.raw(db, "site.name") or t("app.name")
        return JSONResponse({
            "name": name, "short_name": name[:30],
            "lang": "ar", "dir": "rtl", "start_url": "/", "scope": "/",
            "display": "standalone", "background_color": "#F7F8FB",
            "theme_color": "#0848A4",
            "icons": [
                {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        }, media_type="application/manifest+json")

    @app.get("/sw.js")
    async def service_worker():
        # Serve the SW at root scope so it can control the whole app.
        from fastapi.responses import FileResponse
        return FileResponse(config.APP_DIR / "static" / "js" / "sw.js",
                            media_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        key = str(getattr(exc, "detail", "err.generic"))
        if request.url.path.startswith("/api/"):
            data = {"code": key} if key.replace("_", "").isalnum() and key.isupper() else None
            return JSONResponse({"success": False, "message": t(key), "data": data}, status_code=exc.status_code)
        return templates.TemplateResponse(request, "error.html",
            {"request": request, "t": t, "code": exc.status_code, "message_key": key,
             "user": None, "nav": [], "theme": config.DEFAULT_THEME, "sesskey": "",
             "nonce": getattr(request.state, "csp_nonce", ""), "site_name": t("app.name"),
             "themes": config.THEMES, "page_title": t("err.generic")}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"success": False, "message": t("err.field_invalid"), "data": None}, status_code=422)

    @app.exception_handler(401)
    async def unauthorised(request: Request, exc):
        return JSONResponse({"success": False, "message": t(getattr(exc, "detail", "auth.session_expired")),
                             "data": None}, status_code=401)

    @app.exception_handler(429)
    async def throttled(request: Request, exc):
        return JSONResponse({"success": False, "message": t("err.rate_limited"), "data": None},
                             status_code=429)

    @app.exception_handler(404)
    async def not_found(request: Request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"success": False, "message": t("err.not_found"), "data": None},
                                status_code=404)
        return templates.TemplateResponse(request, "error.html",
                                          {"request": request, "t": t, "code": 404,
                                           "message_key": "misc.page_404", "user": None,
                                           "nav": [], "theme": config.DEFAULT_THEME,
                                           "sesskey": "", "nonce": request.state.csp_nonce,
                                           "site_name": t("app.name"), "themes": config.THEMES,
                                           "page_title": t("misc.page_404")}, status_code=404)

    @app.exception_handler(403)
    async def forbidden(request: Request, exc):
        if request.url.path.startswith("/api/"):
            key = str(getattr(exc, "detail", "err.forbidden"))
            data = {"code": key} if key.replace("_", "").isalnum() and key.isupper() else None
            return JSONResponse({"success": False, "message": t(key), "data": data}, status_code=403)
        return templates.TemplateResponse(request, "error.html",
                                          {"request": request, "t": t, "code": 403,
                                           "message_key": "misc.page_403", "user": None,
                                           "nav": [], "theme": config.DEFAULT_THEME,
                                           "sesskey": "", "nonce": request.state.csp_nonce,
                                           "site_name": t("app.name"), "themes": config.THEMES,
                                           "page_title": t("misc.page_403")}, status_code=403)

    @app.exception_handler(500)
    async def server_error(request: Request, exc):
        return templates.TemplateResponse(request, "error.html",
                                          {"request": request, "t": t, "code": 500,
                                           "message_key": "misc.page_500", "user": None,
                                           "nav": [], "theme": config.DEFAULT_THEME,
                                           "sesskey": "", "nonce": getattr(request.state, "csp_nonce", ""),
                                           "site_name": t("app.name"), "themes": config.THEMES,
                                           "page_title": t("misc.page_500")}, status_code=500)

    return app

app = create_app()
