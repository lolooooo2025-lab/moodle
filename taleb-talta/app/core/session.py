"""Server-side session management.

- Cookie holds an opaque random token; the DB stores only sha256(token).
- Idle timeout (30 min) AND absolute timeout (12 h), both enforced in UTC.
- Hijack detection: fingerprint = HMAC(IP + User-Agent); mismatch → destroy +
  audit critical + force re-login.
- sesskey generated per session, rotated on login / privilege change.
- Revocation on logout, password change, ban, admin force-logout.

Inspired by Moodle's session manager (lib/classes/session/manager.php) and
require_sesskey (lib/sessionlib.php:83), re-implemented originally.
"""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app import config
from app.core import security, settings as site_settings
from app.core.audit import audit
from app.models import Session, User, utcnow

async def create_session(db: AsyncSession, user: User, *, ip: str, user_agent: str) -> str:
    """Create a new server-side session; return the raw cookie token."""
    token = security.new_token()
    now = utcnow()
    sess = Session(
        id=security.hash_token(token),
        user_id=user.id,
        sesskey=security.new_sesskey(),
        fingerprint=security.fingerprint(ip, user_agent),
        ip=ip, user_agent=user_agent[:255],
        created_at=now, last_seen=now,
        absolute_expires=now + timedelta(hours=await site_settings.integer(db, "security.session_absolute_hours")),
    )
    db.add(sess)
    await db.flush()
    return token

async def get_session(db: AsyncSession, token: str | None, *, ip: str,
                      user_agent: str) -> tuple[Session | None, User | None, str | None]:
    """Validate a session token. Returns (session, user, error_key).

    error_key is an i18n key when the session is invalid/expired/hijacked.
    """
    if not token:
        return None, None, None
    sid = security.hash_token(token)
    sess = (await db.execute(select(Session).where(Session.id == sid))).scalar_one_or_none()
    if sess is None or sess.revoked:
        return None, None, "auth.session_expired"
    now = utcnow()
    # absolute timeout
    if now >= sess.absolute_expires:
        await revoke_session(db, sess)
        await db.commit()
        return None, None, "auth.session_expired"
    # idle timeout
    if now - sess.last_seen > timedelta(minutes=await site_settings.integer(db, "security.session_idle_minutes")):
        await revoke_session(db, sess)
        await db.commit()
        return None, None, "auth.session_expired"
    # hijack detection
    if sess.fingerprint != security.fingerprint(ip, user_agent):
        await revoke_session(db, sess)
        await audit(db, action="session.hijack_detected", actor_id=sess.user_id,
                    ip=ip, user_agent=user_agent, severity="critical")
        await db.commit()
        return None, None, "auth.session_expired"
    # touch idle clock (commit so the sliding window actually slides)
    sess.last_seen = now
    user = (await db.execute(select(User).where(User.id == sess.user_id))).scalar_one_or_none()
    if user is None or user.status != "active":
        await revoke_session(db, sess)
        await db.commit()
        return None, None, "auth.account_banned"
    await db.commit()
    return sess, user, None

async def rotate_sesskey(db: AsyncSession, sess: Session) -> str:
    sess.sesskey = security.new_sesskey()
    await db.flush()
    return sess.sesskey

async def revoke_session(db: AsyncSession, sess: Session):
    sess.revoked = True
    await db.flush()

async def revoke_all_for_user(db: AsyncSession, user_id: int):
    await db.execute(update(Session).where(Session.user_id == user_id,
                                           Session.revoked == False)  # noqa: E712
                     .values(revoked=True))
    await db.flush()

async def purge_expired(db: AsyncSession):
    """Scheduled cleanup of expired/revoked sessions."""
    cutoff = utcnow() - timedelta(seconds=config.SESSION_ABSOLUTE_SECONDS)
    await db.execute(delete(Session).where(Session.created_at < cutoff))
    await db.flush()
