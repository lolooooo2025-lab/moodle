"""Authentication service — register / login / logout / forgot / reset.

Egyptian phone+password+guardian+division registration (spec §9). Login enforces
per-account AND per-IP lockout, audits every attempt, rotates the session on
login (fixation defence), and stores a fingerprint for hijack detection.
All user-facing messages are i18n keys (Egyptian Arabic).
"""
from __future__ import annotations
import re
from datetime import timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core import security, session as sessmgr, ratelimit
from app.core.audit import audit
from app.core.events import bus
from app.core import community, moderation, settings as site_settings
from app.core.capabilities import tt_can
from app.core.i18n import t
from app.models import (User, Division, LoginAttempt, PasswordResetToken,
                        PasswordHistory, utcnow)

PHONE_RE = re.compile(r"^01[0125][0-9]{8}$")

def normalize_phone(raw: str) -> str:
    digits = re.sub(r"[\s\-+]", "", raw or "")
    if digits.startswith("20"):
        digits = "0" + digits[2:]
    if digits.startswith("0020"):
        digits = "0" + digits[4:]
    return digits

def valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone))

class AuthError(Exception):
    def __init__(self, key: str, field: str = ""):
        self.key = key
        self.field = field
        super().__init__(key)

async def register(db: AsyncSession, *, phone: str, password: str, name: str,
                   guardian_phone: str, division_id: int | None,
                   ip: str = "", user_agent: str = "") -> User:
    if not await site_settings.boolean(db, "site.registration_enabled"):
        raise AuthError("site.registration_closed")
    phone = normalize_phone(phone)
    guardian_phone = normalize_phone(guardian_phone)
    if not name or not name.strip():
        raise AuthError("err.required", "name")
    if moderation.filter_text(name, await moderation.dictionary(db))[1]:
        raise AuthError("err.name_not_allowed", "name")
    if not valid_phone(phone):
        raise AuthError("err.invalid_phone", "phone")
    if not valid_phone(guardian_phone):
        raise AuthError("err.invalid_phone", "guardian_phone")
    if division_id is None:
        raise AuthError("err.division_required", "division_id")
    div = (await db.execute(select(Division).where(Division.id == division_id))).scalar_one_or_none()
    if div is None:
        raise AuthError("err.division_required", "division_id")
    policy = security.password_policy_errors(password, phone, await site_settings.integer(db, "security.password_min_length"))
    if policy:
        raise AuthError(policy[0], "password")
    exists = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if exists:
        raise AuthError("err.user_exists", "phone")
    # rate limit registration per IP
    if not await ratelimit.hit(db, f"reg:{ip}", limit=10, window=3600):
        raise AuthError("err.rate_limited")
    user = User(phone=phone, password_hash=security.hash_password(password),
                name=name.strip(), guardian_phone=guardian_phone,
                division_id=division_id, role="student", status="active")
    db.add(user)
    await db.flush()
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    await community.add_division_member(db, user)
    await audit(db, action="user.registered", actor=user, entity_type="user",
                entity_id=user.id, ip=ip, user_agent=user_agent, severity="notice")
    await bus.dispatch("user.registered", {"user_id": user.id})
    return user

async def _record_attempt(db, phone, ip, success):
    db.add(LoginAttempt(phone=phone, ip=ip, success=success))
    await db.flush()

async def login(db: AsyncSession, *, phone: str, password: str,
                ip: str = "", user_agent: str = "") -> tuple[User, str]:
    """Return (user, session_token). Raises AuthError with an Egyptian key."""
    phone = normalize_phone(phone)
    # per-IP rate limit
    security_values = await site_settings.security_policy(db)
    if not await ratelimit.hit(db, f"login_ip:{ip}", limit=security_values["security.login_max_ip"], window=300):
        await db.commit()                      # persist the rate-limit hit
        raise AuthError("err.too_many_attempts")
    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    now = utcnow()
    # account lockout
    if user and user.locked_until and now < user.locked_until:
        await _record_attempt(db, phone, ip, False)
        await db.commit()                      # persist the failed attempt
        raise AuthError("err.account_locked")
    if user and user.status == "banned":
        await _record_attempt(db, phone, ip, False)
        await audit(db, action="user.banned_login_attempt", actor_id=user.id,
                    entity_type="user", entity_id=user.id,
                    ip=ip, user_agent=user_agent, severity="critical")
        await db.commit()                      # persist attempt + audit
        raise AuthError("auth.account_banned")
    if user and user.status != "active":
        await _record_attempt(db, phone, ip, False)
        await db.commit()
        raise AuthError("auth.account_inactive")
    ok = False
    needs_rehash = False
    if user:
        ok, needs_rehash = security.verify_password(password, user.password_hash)
    if not ok:
        await _record_attempt(db, phone, ip, False)
        if user:
            user.failed_attempts += 1
            if user.failed_attempts >= security_values["security.login_max_account"]:
                user.locked_until = now + timedelta(minutes=security_values["security.lockout_minutes"])
                user.failed_attempts = 0
                await audit(db, action="user.locked_out", actor_id=user.id,
                            ip=ip, user_agent=user_agent, severity="warning")
            await db.flush()
        await audit(db, action="user.login_failed", actor_id=user.id if user else None,
                    ip=ip, user_agent=user_agent, severity="notice",
                    after={"phone": phone})
        await bus.dispatch("user.login_failed", {"phone": phone, "ip": ip})
        await db.commit()                      # persist counter + lockout + audit
        raise AuthError("err.login_failed")
    # A scoped communication/evaluation ban does not block course access.
    # Record an admin alert on every login while the restriction is active.
    restriction = await moderation.active_restriction(db, user.id)
    if restriction:
        await audit(db, action="user.banned_login_attempt", actor=user,
                    entity_type="user", entity_id=user.id,
                    after={"scope": restriction.scope, "expires_at": restriction.expires_at.isoformat()},
                    ip=ip, user_agent=user_agent, severity="critical")
    if await site_settings.boolean(db, "site.maintenance") and not await tt_can(db, user, "site/settings"):
        await _record_attempt(db, phone, ip, False)
        await db.commit()
        raise AuthError("site.maintenance")
    # success
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = now
    if needs_rehash:
        user.password_hash = security.hash_password(password)
    await db.flush()
    await _record_attempt(db, phone, ip, True)
    # rotate: revoke old sessions, create a fresh one (session-fixation defence)
    await sessmgr.revoke_all_for_user(db, user.id)
    token = await sessmgr.create_session(db, user, ip=ip, user_agent=user_agent)
    await audit(db, action="user.logged_in", actor=user, ip=ip,
                user_agent=user_agent, severity="info")
    await bus.dispatch("user.logged_in", {"user_id": user.id})
    return user, token

async def logout(db: AsyncSession, sess, user, *, ip="", user_agent=""):
    await sessmgr.revoke_session(db, sess)
    await audit(db, action="user.logged_out", actor=user, ip=ip, user_agent=user_agent)
    await bus.dispatch("user.logged_out", {"user_id": user.id})

async def forgot_password(db: AsyncSession, *, phone: str, ip="") -> str | None:
    """Create a reset token. Returns the raw token ONLY in debug (for testing);
    production delivers it out-of-band and returns None."""
    phone = normalize_phone(phone)
    if not await ratelimit.hit(db, f"reset:{ip}", limit=5, window=3600):
        raise AuthError("err.rate_limited")
    user = (await db.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if user is None:
        # Do not reveal whether the phone exists.
        return None
    raw = security.new_token()
    db.add(PasswordResetToken(user_id=user.id, token_hash=security.hash_token(raw),
                              expires_at=utcnow() + timedelta(minutes=30)))
    await audit(db, action="user.password_reset_requested", actor_id=user.id, ip=ip,
                severity="notice")
    await db.flush()
    return raw if config.DEBUG else None

async def reset_password(db: AsyncSession, *, token: str, new_password: str, ip="") -> User:
    th = security.hash_token(token)
    row = (await db.execute(select(PasswordResetToken).where(
        PasswordResetToken.token_hash == th))).scalar_one_or_none()
    if row is None or row.status != "pending" or utcnow() >= row.expires_at:
        raise AuthError("err.csrf")
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one_or_none()
    if user is None:
        raise AuthError("err.user_not_found")
    policy = security.password_policy_errors(new_password, user.phone, await site_settings.integer(db, "security.password_min_length"))
    if policy:
        raise AuthError(policy[0], "password")
    await _check_history(db, user.id, new_password)
    user.password_hash = security.hash_password(new_password)
    user.password_changed_at = utcnow()
    row.status = "used"
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    await community.add_division_member(db, user)
    await sessmgr.revoke_all_for_user(db, user.id)   # force re-login everywhere
    await audit(db, action="user.password_changed", actor=user, ip=ip, severity="notice")
    await bus.dispatch("user.password_changed", {"user_id": user.id})
    await db.flush()
    return user

async def _check_history(db: AsyncSession, user_id: int, new_password: str):
    rows = (await db.execute(select(PasswordHistory).where(
        PasswordHistory.user_id == user_id).order_by(
        PasswordHistory.created_at.desc()).limit(await site_settings.integer(db, "security.password_history")))).scalars().all()
    for r in rows:
        ok, _ = security.verify_password(new_password, r.password_hash)
        if ok:
            raise AuthError("err.password_reused", "password")

async def change_password(db: AsyncSession, user: User, *, current: str, new: str, ip=""):
    ok, _ = security.verify_password(current, user.password_hash)
    if not ok:
        raise AuthError("err.password_wrong_current", "current_password")
    policy = security.password_policy_errors(new, user.phone, await site_settings.integer(db, "security.password_min_length"))
    if policy:
        raise AuthError(policy[0], "password")
    await _check_history(db, user.id, new)
    user.password_hash = security.hash_password(new)
    user.password_changed_at = utcnow()
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    await community.add_division_member(db, user)
    await sessmgr.revoke_all_for_user(db, user.id)
    await audit(db, action="user.password_changed", actor=user, ip=ip, severity="notice")
    await db.flush()
