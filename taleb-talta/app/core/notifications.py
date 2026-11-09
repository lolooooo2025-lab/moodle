"""Targeted in-app notifications, Friday campaigns and best-effort Web Push."""
from __future__ import annotations
import asyncio, base64, hashlib, hmac, json
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, insert, update, delete, func, literal, or_
from sqlalchemy.exc import IntegrityError
from app import config
from app.core import moderation
from app.core.customization import safe_url
from app.core.audit import audit
from app.models import (Notification, NotificationRecipient, Campaign, PushSubscription,
                        User, Course, CourseStudent, Division, utcnow)

ROLES = ("owner", "admin", "moderator", "teacher", "student", "parent")
AUDIENCES = ("all", "role", "division", "course", "user")
# Exact providers, plus subdomains only where the provider allocates them.
PUSH_HOSTS = ("push.services.mozilla.com", "fcm.googleapis.com", "android.googleapis.com",
              "notify.windows.com", "web.push.apple.com", "push.apple.com")
PUSH_EXACT_HOSTS = {"fcm.googleapis.com", "android.googleapis.com", "web.push.apple.com"}
MAX_PUSH_DEVICES = 5


def vapid_keys():
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    # The persisted secret is key material; derive a valid P-256 scalar from it.
    order = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
    raw = hmac.new(config.VAPID_PRIVATE_KEY.encode(), b"taleb-talta:vapid:p256", hashlib.sha256).digest()
    scalar = int.from_bytes(raw, "big") % (order - 1) + 1
    private = ec.derive_private_key(scalar, ec.SECP256R1())
    public = private.public_key().public_bytes(serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint)
    pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return base64.urlsafe_b64encode(public).decode().rstrip("="), pem


def validate_subscription(endpoint: str, p256dh: str, auth: str):
    try:
        parsed = urlparse(endpoint)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        raise HTTPException(422, "notif.push_endpoint_invalid")
    if (parsed.scheme != "https" or parsed.username or parsed.password or port not in (None, 443)
            or endpoint != endpoint.strip() or any(ord(c) < 32 for c in endpoint) or len(endpoint) > 2048):
        raise HTTPException(422, "notif.push_endpoint_invalid")
    if not any(host == h or (h not in PUSH_EXACT_HOSTS and host.endswith("." + h)) for h in PUSH_HOSTS):
        raise HTTPException(422, "notif.push_endpoint_invalid")
    try:
        pad = lambda s: s + "=" * (-len(s) % 4)
        point = base64.urlsafe_b64decode(pad(p256dh))
        secret = base64.urlsafe_b64decode(pad(auth))
        if len(point) != 65 or point[0] != 4 or not 16 <= len(secret) <= 32:
            raise ValueError()
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except (ValueError, TypeError):
        raise HTTPException(422, "notif.push_keys_invalid")


async def _audience_users(db, data: dict):
    audience = data.get("audience", "all")
    if audience not in AUDIENCES:
        raise HTTPException(422, "notif.audience_invalid")
    q = select(User.id).where(User.status == "active")
    role, div, course, uid = data.get("role", ""), int(data.get("division_id") or 0), int(data.get("course_id") or 0), int(data.get("user_id") or 0)
    if audience == "role":
        if role not in ROLES:
            raise HTTPException(422, "notif.audience_invalid")
        q = q.where(User.role == role)
    elif audience == "division":
        if not div or not (await db.execute(select(Division.id).where(Division.id == div))).first():
            raise HTTPException(422, "notif.audience_invalid")
        q = q.where(User.division_id == div)
    elif audience == "course":
        if not course or not (await db.execute(select(Course.id).where(Course.id == course, Course.deleted_at.is_(None)))).first():
            raise HTTPException(422, "notif.audience_invalid")
        q = q.where(User.id.in_(select(CourseStudent.user_id).where(CourseStudent.course_id == course)))
    elif audience == "user":
        if not uid:
            raise HTTPException(422, "notif.audience_invalid")
        q = q.where(User.id == uid)
    elif role or div or course or uid:
        raise HTTPException(422, "notif.audience_invalid")
    return q


async def _fanout(db, notification_id: int, user_query):
    stmt = insert(NotificationRecipient).from_select(
        ["notification_id", "user_id", "push_status", "created_at"],
        select(literal(notification_id), user_query.subquery().c.id, literal("pending"), literal(utcnow())))
    result = await db.execute(stmt)
    return result.rowcount or 0


async def send_targeted(db, actor, data: dict, *, ip=""):
    screened = await moderation.screen(db, actor, {"title": data["title"], "body": data["body"]},
                                       source="notification.send", count_strike=False)
    url = safe_url(data.get("url") or "/notifications")
    users = await _audience_users(db, data)
    n = Notification(kind="targeted", title=screened.values["title"].strip()[:200],
                     body=screened.values["body"], url=url,
                     audience_role=data.get("role", "") if data.get("audience") == "role" else "",
                     division_id=int(data.get("division_id") or 0) or None if data.get("audience") == "division" else None,
                     course_id=int(data.get("course_id") or 0) or None if data.get("audience") == "course" else None,
                     user_id=int(data.get("user_id") or 0) or None if data.get("audience") == "user" else None,
                     created_by=actor.id)
    if not n.title or not n.body.strip():
        raise HTTPException(422, "err.required")
    db.add(n); await db.flush()
    count = await _fanout(db, n.id, users)
    await audit(db, action="broadcast.sent", actor=actor, entity_type="notification", entity_id=n.id,
                after={"audience": data.get("audience"), "recipients": count}, ip=ip, severity="notice")
    return n, count


async def notify_user(db, user_id: int, title_key: str, body_key: str, *, kind="system", url="/notifications", title_params=None, body_params=None):
    from app.core.i18n import t
    n = Notification(kind=kind, title=t(title_key, **(title_params or {})),
                     body=t(body_key, **(body_params or {})), url=safe_url(url))
    db.add(n); await db.flush()
    await _fanout(db, n.id, select(User.id).where(User.id == user_id, User.status == "active"))
    return n


def campaign_time(week: date) -> datetime:
    if week.weekday() != 4:
        raise HTTPException(422, "campaign.friday_required")
    local = datetime.combine(week, time(config.FRIDAY_CAMPAIGN_HOUR, 0), ZoneInfo(config.SITE_TIMEZONE))
    return local.astimezone(timezone.utc)


async def save_campaign(db, actor, data: dict, campaign_id: int | None = None, *, ip=""):
    week = data["week_date"] if isinstance(data["week_date"], date) else date.fromisoformat(data["week_date"])
    publish_at = campaign_time(week)
    today = datetime.now(ZoneInfo(config.SITE_TIMEZONE)).date()
    if week < today:
        raise HTTPException(422, "campaign.date_past")
    screened = await moderation.screen(db, actor, {"title": data["title"], "body": data["body"]},
                                       source="campaign.save", count_strike=False)
    row = None
    if campaign_id:
        row = (await db.execute(select(Campaign).where(Campaign.id == campaign_id).with_for_update())).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "err.not_found")
        if row.status != "scheduled":
            raise HTTPException(409, "campaign.not_editable")
    if row is None:
        row = Campaign(created_by=actor.id)
        db.add(row)
    row.week_date, row.title, row.body = week, screened.values["title"].strip()[:200], screened.values["body"]
    row.publish_at, row.status = publish_at, "scheduled"
    if not row.title or not row.body.strip():
        raise HTTPException(422, "err.required")
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(409, "campaign.week_taken")
    await audit(db, action="campaign.saved", actor=actor, entity_type="campaign", entity_id=row.id,
                after={"week": week.isoformat(), "publish_at": publish_at.isoformat()}, ip=ip)
    return row


async def publish_campaign(db, campaign: Campaign, actor_id: int | None = None):
    campaign = (await db.execute(select(Campaign).where(Campaign.id == campaign.id).with_for_update())).scalar_one()
    if campaign.status == "published":
        return None, 0
    if campaign.status != "scheduled":
        raise HTTPException(409, "campaign.not_editable")
    n = Notification(kind="campaign", title=campaign.title, body=campaign.body,
                     url=f"/campaigns/{campaign.id}", campaign_id=campaign.id, created_by=actor_id)
    db.add(n); await db.flush()
    count = await _fanout(db, n.id, select(User.id).where(User.status == "active"))
    campaign.status, campaign.published_at = "published", utcnow()
    await audit(db, action="campaign.published", actor_id=actor_id, entity_type="campaign",
                entity_id=campaign.id, after={"notification_id": n.id, "recipients": count}, severity="notice")
    return n, count


async def publish_due_campaigns(db):
    rows = (await db.execute(select(Campaign).where(Campaign.status == "scheduled",
                Campaign.publish_at <= utcnow()).order_by(Campaign.publish_at).limit(10))).scalars().all()
    published = 0
    for row in rows:
        await publish_campaign(db, row)
        published += 1
    return {"campaigns": published}


def notification_public(n: Notification, read_at=None):
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "url": n.url,
            "campaign_id": n.campaign_id, "created_at": n.created_at.isoformat(),
            "read": read_at is not None, "read_at": read_at.isoformat() if read_at else ""}


async def inbox(db, user, limit=100):
    limit = min(max(limit, 1), 100)
    targeted = (await db.execute(select(Notification, NotificationRecipient.read_at)
                  .join(NotificationRecipient, NotificationRecipient.notification_id == Notification.id)
                  .where(NotificationRecipient.user_id == user.id, Notification.kind != "campaign")
                  .order_by(Notification.created_at.desc()).limit(limit))).all()
    campaigns = (await db.execute(select(Notification, NotificationRecipient.read_at)
                   .outerjoin(NotificationRecipient, (NotificationRecipient.notification_id == Notification.id)
                              & (NotificationRecipient.user_id == user.id))
                   .where(Notification.kind == "campaign").order_by(Notification.created_at.desc()).limit(limit))).all()
    rows = [notification_public(n, r) for n, r in targeted + campaigns]
    rows.sort(key=lambda x: x["created_at"], reverse=True)
    unread = (await db.execute(select(func.count(NotificationRecipient.id))
        .join(Notification, Notification.id == NotificationRecipient.notification_id)
        .where(NotificationRecipient.user_id == user.id, NotificationRecipient.read_at.is_(None),
               Notification.kind != "campaign"))).scalar_one()
    unseen_campaigns = (await db.execute(select(func.count(Notification.id)).where(
        Notification.kind == "campaign", ~select(NotificationRecipient.id).where(
            NotificationRecipient.notification_id == Notification.id,
            NotificationRecipient.user_id == user.id, NotificationRecipient.read_at.is_not(None)).exists()))).scalar_one()
    return rows[:limit], unread + unseen_campaigns


async def mark_read(db, user, notification_id: int):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    n = (await db.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
    if n is None:
        raise HTTPException(404, "err.not_found")
    if n.kind == "campaign":
        # Concurrent first reads are safe: the unique recipient row is created once.
        await db.execute(pg_insert(NotificationRecipient).values(notification_id=n.id, user_id=user.id,
            push_status="skipped", created_at=utcnow()).on_conflict_do_nothing(index_elements=["notification_id", "user_id"]))
    result = await db.execute(update(NotificationRecipient).where(
        NotificationRecipient.notification_id == n.id, NotificationRecipient.user_id == user.id,
        NotificationRecipient.read_at.is_(None)).values(read_at=utcnow()))
    if n.kind != "campaign" and not result.rowcount:
        exists = (await db.execute(select(NotificationRecipient.id).where(
            NotificationRecipient.notification_id == n.id, NotificationRecipient.user_id == user.id))).first()
        if not exists:
            raise HTTPException(403, "err.forbidden")


async def mark_all_read(db, user):
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    await db.execute(update(NotificationRecipient).where(
        NotificationRecipient.user_id == user.id, NotificationRecipient.read_at.is_(None)).values(read_at=utcnow()))
    campaigns = select(Notification.id).where(Notification.kind == "campaign",
        ~select(NotificationRecipient.id).where(NotificationRecipient.notification_id == Notification.id,
            NotificationRecipient.user_id == user.id).exists())
    await db.execute(pg_insert(NotificationRecipient).from_select(
        ["notification_id", "user_id", "read_at", "push_status", "created_at"],
        select(campaigns.subquery().c.id, literal(user.id), literal(utcnow()), literal("skipped"), literal(utcnow()))
    ).on_conflict_do_nothing(index_elements=["notification_id", "user_id"]))


async def dispatch_push(db):
    """Best-effort device delivery; in-app read state never depends on push.

    At most 10 recipients × 5 devices per run. The provider session forbids
    redirects, so an allowlisted endpoint cannot bounce the request to an
    internal address. sent/failed count device attempts, not read state.
    """
    from pywebpush import webpush, WebPushException
    import requests
    recipients = (await db.execute(select(NotificationRecipient, Notification)
        .join(Notification, Notification.id == NotificationRecipient.notification_id)
        .where(NotificationRecipient.push_status == "pending")
        .order_by(NotificationRecipient.id).limit(10))).all()
    _, pem = vapid_keys()
    counts = {"sent": 0, "failed": 0, "removed": 0, "skipped": 0, "recipients": 0}
    session = requests.Session()
    session.max_redirects = 0
    try:
        for recipient, notification in recipients:
            subs = (await db.execute(select(PushSubscription).where(
                PushSubscription.user_id == recipient.user_id).order_by(PushSubscription.id))).scalars().all()
            if not subs:
                recipient.push_status, recipient.push_attempted_at = "skipped", utcnow()
                counts["skipped"] += 1
                continue
            payload = json.dumps({"title": notification.title, "body": notification.body,
                                  "url": notification.url, "notification_id": notification.id}, ensure_ascii=False)
            succeeded = 0
            for sub in subs:
                try:
                    validate_subscription(sub.endpoint, sub.p256dh, sub.auth)
                    await asyncio.to_thread(webpush, subscription_info={"endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data=payload,
                        vapid_private_key=pem, vapid_claims={"sub": config.VAPID_SUBJECT},
                        ttl=3600, timeout=5, requests_session=session)
                    sub.failure_count, sub.last_success = 0, utcnow()
                    succeeded += 1
                    counts["sent"] += 1
                except Exception as exc:
                    code = getattr(getattr(exc, "response", None), "status_code", 0)
                    sub.failure_count += 1
                    if code in (404, 410) or sub.failure_count >= 10:
                        await db.delete(sub); counts["removed"] += 1
                    counts["failed"] += 1
            recipient.push_status = "sent" if succeeded else "failed"
            recipient.push_attempted_at = utcnow()
            counts["recipients"] += 1
    finally:
        session.close()
    # Bounded bulk skip for device-less recipients; the next run handles the rest.
    ids = (await db.execute(select(NotificationRecipient.id).where(
        NotificationRecipient.push_status == "pending",
        ~select(PushSubscription.id).where(PushSubscription.user_id == NotificationRecipient.user_id).exists()
    ).order_by(NotificationRecipient.id).limit(500))).scalars().all()
    if ids:
        await db.execute(update(NotificationRecipient).where(NotificationRecipient.id.in_(ids))
                         .values(push_status="skipped", push_attempted_at=utcnow()))
        counts["skipped"] += len(ids)
    return counts
