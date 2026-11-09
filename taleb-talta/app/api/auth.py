"""Auth JSON API. Envelope {success, message, data}; Egyptian messages.

Login sets an HttpOnly/SameSite cookie; the sesskey is returned in data so the
client can send it as X-Sesskey on subsequent writes.
"""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core.db import get_db
from app.core import auth
from app.core.i18n import t
from app.api.deps import (envelope, client_ip, user_agent, current_session,
                          require_user, check_csrf)

router = APIRouter(prefix="/api/auth", tags=["auth"])

class RegisterIn(BaseModel):
    phone: str
    password: str
    name: str
    guardian_phone: str
    division_id: int
    website: str = ""          # honeypot — must stay empty
    elapsed_ms: int = 0        # min time-to-submit

class LoginIn(BaseModel):
    phone: str
    password: str

class ForgotIn(BaseModel):
    phone: str

class ResetIn(BaseModel):
    token: str
    new_password: str

class ChangeIn(BaseModel):
    current_password: str
    new_password: str

def _cookie_attrs(request: Request) -> dict:
    """Cookie attributes for the session cookie.

    Local plain-HTTP dev keeps the stricter Lax. Over HTTPS (including the
    cross-site preview iframe) we need SameSite=None; Secure; Partitioned
    (CHIPS). `Partitioned` is what lets the cookie survive browsers that block
    third-party cookies: the cookie is keyed to the top-level site + app origin
    instead of being a shared third-party cookie. CSRF is still covered by
    sesskey + Origin checks regardless of SameSite.
    """
    proto = request.headers.get("x-forwarded-proto", "")
    origin = request.headers.get("origin", "") or request.headers.get("referer", "")
    https = (proto == "https" or request.url.scheme == "https"
             or origin.startswith("https:") or config.SESSION_COOKIE_SECURE)
    if https:
        return {"secure": True, "samesite": "None",
                "partitioned": config.SESSION_COOKIE_PARTITIONED}
    return {"secure": False, "samesite": "Lax", "partitioned": False}

def _set_cookie(response: Response, token: str, request: Request,
                max_age: int = config.SESSION_ABSOLUTE_SECONDS):
    # Build the Set-Cookie header by hand: Starlette's set_cookie(partitioned=)
    # raises on Python < 3.14, but the CHIPS `Partitioned` attribute is just a
    # flag in the header and is understood by current browsers regardless.
    attrs = _cookie_attrs(request)
    parts = [f"{config.SESSION_COOKIE}={token}", "Path=/", f"Max-Age={max_age}", "HttpOnly"]
    if attrs["secure"]:
        parts.append("Secure")
    parts.append(f"SameSite={attrs['samesite']}")
    if attrs["partitioned"]:
        parts.append("Partitioned")
    response.headers.append("Set-Cookie", "; ".join(parts))

@router.post("/register")
async def register(body: RegisterIn, request: Request, response: Response,
                   db: AsyncSession = Depends(get_db)):
    # honeypot + min time-to-submit (prompt §7.8)
    if body.website or body.elapsed_ms < 1500:
        return envelope(False, "err.rate_limited")
    try:
        user = await auth.register(db, phone=body.phone, password=body.password,
                                   name=body.name, guardian_phone=body.guardian_phone,
                                   division_id=body.division_id, ip=client_ip(request),
                                   user_agent=user_agent(request))
        await db.commit()
        return envelope(True, "auth.registered", {"user_id": user.id})
    except auth.AuthError as e:
        await db.rollback()
        return envelope(False, e.key)

@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)):
    try:
        user, token = await auth.login(db, phone=body.phone, password=body.password,
                                       ip=client_ip(request), user_agent=user_agent(request))
        sess, _, _ = await current_session(request, db)
        # fetch the fresh session to read its sesskey
        from app.core import security
        from sqlalchemy import select
        from app.models import Session
        s = (await db.execute(select(Session).where(
            Session.id == security.hash_token(token)))).scalar_one()
        await db.commit()
        _set_cookie(response, token, request)
        return envelope(True, "auth.logged_in",
                        {"user_id": user.id, "role": user.role, "name": user.name,
                         "sesskey": s.sesskey})
    except auth.AuthError as e:
        await db.rollback()
        return envelope(False, e.key)

@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user:
        await check_csrf(request, sess)
        await auth.logout(db, sess, user, ip=client_ip(request), user_agent=user_agent(request))
        await db.commit()
    # Expire the cookie with the SAME attributes it was set with, otherwise the
    # browser keeps the partitioned/secure variant.
    _set_cookie(response, "", request, max_age=0)
    return envelope(True, "auth.logged_out")

@router.post("/forgot")
async def forgot(body: ForgotIn, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        raw = await auth.forgot_password(db, phone=body.phone, ip=client_ip(request))
        await db.commit()
        data = {"token": raw} if raw else None
        return envelope(True, "auth.password_reset_sent", data)
    except auth.AuthError as e:
        await db.rollback()
        return envelope(False, e.key)

@router.post("/reset")
async def reset(body: ResetIn, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await auth.reset_password(db, token=body.token, new_password=body.new_password,
                                  ip=client_ip(request))
        await db.commit()
        return envelope(True, "ok.password_changed")
    except auth.AuthError as e:
        await db.rollback()
        return envelope(False, e.key)

@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user, err = await current_session(request, db)
    if user is None:
        return envelope(False, err or "auth.session_expired")
    from app.core import moderation
    restriction = await moderation.active_restriction(db, user.id)
    return envelope(True, "", {"user_id": user.id, "name": user.name, "role": user.role,
                               "restricted": restriction is not None,
                               "restricted_until": restriction.expires_at.isoformat() if restriction else None,
                               "phone": user.phone, "division_id": user.division_id,
                               "title": user.title, "badge": user.badge,
                               "sesskey": sess.sesskey})

@router.post("/change_password")
async def change_password(body: ChangeIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    try:
        await auth.change_password(db, user, current=body.current_password,
                                   new=body.new_password, ip=client_ip(request))
        await db.commit()
        return envelope(True, "ok.password_changed")
    except auth.AuthError as e:
        await db.rollback()
        return envelope(False, e.key)
