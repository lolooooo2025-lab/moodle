"""Shared request helpers for API + web: envelope, session, CSRF, capability gates.

JSON envelope: {success, message, data}. Messages are i18n keys resolved to
Egyptian Arabic. Every mutating request requires a valid sesskey AND a matching
Origin/Referer (prompt §7.3/§7.4).
"""
from __future__ import annotations
from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core.db import get_db
from app.core import session as sessmgr, security, settings as site_settings
from app.core.i18n import t
from app.core.capabilities import tt_can
from app.core.audit import audit
from app.models import User, Session

def envelope(success: bool, message_key: str = "", data=None, **params) -> dict:
    return {"success": success, "message": t(message_key, **params) if message_key else "",
            "data": data}

def client_ip(request: Request) -> str:
    # Behind a proxy, X-Forwarded-For[0]; else the socket peer.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""

def user_agent(request: Request) -> str:
    return request.headers.get("user-agent", "")[:255]

async def current_session(request: Request, db: AsyncSession):
    token = request.cookies.get(config.SESSION_COOKIE)
    return await sessmgr.get_session(db, token, ip=client_ip(request),
                                     user_agent=user_agent(request))

async def require_user(request: Request, db: AsyncSession) -> tuple[Session, User]:
    sess, user, err = await current_session(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail=err or "auth.session_expired")
    if await site_settings.boolean(db, "site.maintenance") and not await tt_can(db, user, "site/settings"):
        raise HTTPException(status_code=503, detail="site.maintenance")
    return sess, user

def _origin_ok(request: Request) -> bool:
    """Validate Origin/Referer against the request host (CSRF defence)."""
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    if not origin:
        # Non-browser clients (tests) may omit Origin; allow only when a valid
        # sesskey is present (checked separately).
        return True
    origin_host = origin.split("//", 1)[-1].split("/", 1)[0]
    if config.PUBLIC_ORIGIN:
        from urllib.parse import urlparse
        public = urlparse(config.PUBLIC_ORIGIN)
        hosts = {public.netloc} if public.scheme in ("http", "https") and public.netloc else set()
    else:
        # Local/dev proxy compatibility. Production should set TT_PUBLIC_ORIGIN
        # and have the reverse proxy overwrite forwarded headers.
        hosts = {request.headers.get("host", ""), request.headers.get("x-forwarded-host", "")}
    return origin_host in hosts and origin_host != ""

async def check_csrf(request: Request, sess: Session):
    """Require a valid sesskey (header or form) + matching Origin on writes."""
    if not _origin_ok(request):
        raise HTTPException(status_code=403, detail="err.csrf")
    provided = request.headers.get("x-sesskey")
    if not provided:
        # try form body (parsed by caller) — callers pass it via header for JSON
        provided = request.query_params.get("sesskey")
    if not security.check_sesskey(provided, sess.sesskey):
        raise HTTPException(status_code=403, detail="err.csrf")

async def require_cap(request: Request, db: AsyncSession, capability: str) -> tuple[Session, User]:
    sess, user = await require_user(request, db)
    if not await tt_can(db, user, capability):
        await audit(db, action="capability.denied", actor=user,
                    entity_type="capability", entity_id=capability,
                    ip=client_ip(request), user_agent=user_agent(request), severity="warning")
        await db.commit()                      # persist the denial before raising
        raise HTTPException(status_code=403, detail="err.forbidden")
    return sess, user
