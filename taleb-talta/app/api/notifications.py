"""Notification inbox, targeted compose, Friday campaign archive and Web Push."""
from __future__ import annotations
from datetime import date, datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import notifications as core, ratelimit
from app.core.audit import audit
from app.core.events import bus
from app.api.deps import envelope, require_user, require_cap, check_csrf, client_ip, user_agent
from app.models import (Notification, NotificationRecipient, Campaign, PushSubscription,
                        Division, Course, User, utcnow)

router = APIRouter(tags=["notifications"])


class ComposeIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    url: str = Field(default="/notifications", max_length=255)
    audience: str = "all"
    role: str = ""
    division_id: int = 0
    course_id: int = 0
    user_id: int = 0

class CampaignIn(BaseModel):
    week_date: date
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)

class PushIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2048)
    p256dh: str = Field(min_length=80, max_length=120)
    auth: str = Field(min_length=22, max_length=40)


@router.get("/api/notifications")
async def inbox(request: Request, limit: int = 100, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows, unread = await core.inbox(db, user, limit)
    return envelope(True, "", {"rows": rows, "unread": unread})


@router.get("/api/notifications/unread")
async def unread(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(Notification, NotificationRecipient.read_at)
             .join(NotificationRecipient, NotificationRecipient.notification_id == Notification.id)
             .where(NotificationRecipient.user_id == user.id, NotificationRecipient.read_at.is_(None),
                    Notification.kind != "campaign").order_by(Notification.created_at.desc()).limit(10))).all()
    _, count = await core.inbox(db, user, 1)
    return envelope(True, "", {"unread": count, "latest": [core.notification_public(n, r) for n, r in rows]})


@router.post("/api/notifications/{notification_id}/read")
async def read(notification_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    await core.mark_read(db, user, notification_id)
    await db.commit()
    return envelope(True, "notif.read")


@router.post("/api/notifications/read-all")
async def read_all(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    await core.mark_all_read(db, user)
    await db.commit()
    return envelope(True, "notif.read")


@router.get("/api/admin/notifications/meta")
async def meta(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "broadcast/send")
    divisions = (await db.execute(select(Division.id, Division.name).order_by(Division.name))).all()
    courses = (await db.execute(select(Course.id, Course.title).where(Course.deleted_at.is_(None)).order_by(Course.title))).all()
    return envelope(True, "", {"roles": list(core.ROLES), "audiences": list(core.AUDIENCES),
        "divisions": [{"id": d.id, "name": d.name} for d in divisions],
        "courses": [{"id": c.id, "title": c.title} for c in courses]})


@router.get("/api/admin/notifications/users")
async def find_users(request: Request, q: str = "", db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "broadcast/send")
    q = q.strip()
    if len(q) < 2:
        return envelope(True, "", [])
    rows = (await db.execute(select(User.id, User.name, User.phone, User.role).where(
        User.status == "active", (User.name.ilike(f"%{q}%")) | (User.phone.ilike(f"%{q}%"))).limit(20))).all()
    return envelope(True, "", [{"id": r.id, "name": r.name, "phone": r.phone, "role": r.role} for r in rows])


@router.get("/api/admin/notifications")
async def history(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "broadcast/send")
    rows = (await db.execute(select(Notification, func.count(NotificationRecipient.id))
             .outerjoin(NotificationRecipient, NotificationRecipient.notification_id == Notification.id)
             .group_by(Notification.id).order_by(Notification.created_at.desc()).limit(100))).all()
    return envelope(True, "", [{**core.notification_public(n), "recipients": count} for n, count in rows])


@router.post("/api/admin/notifications")
async def compose(body: ComposeIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "broadcast/send")
    await check_csrf(request, sess)
    if not await ratelimit.hit(db, f"broadcast:{user.id}", 20, 3600):
        await db.commit(); raise HTTPException(429, "err.rate_limited")
    n, count = await core.send_targeted(db, user, body.model_dump(), ip=client_ip(request))
    await db.commit()
    await bus.dispatch("broadcast.sent", {"notification_id": n.id, "recipients": count})
    return envelope(True, "ok.broadcast_sent", {"id": n.id, "recipients": count})


@router.get("/api/campaigns")
async def archive(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    rows = (await db.execute(select(Campaign, Notification, NotificationRecipient.read_at)
             .join(Notification, Notification.campaign_id == Campaign.id)
             .outerjoin(NotificationRecipient, (NotificationRecipient.notification_id == Notification.id)
                        & (NotificationRecipient.user_id == user.id))
             .where(Campaign.status == "published").order_by(Campaign.week_date.desc()).limit(100))).all()
    out = []
    for c, n, r in rows:
        data = core.notification_public(n, r)
        data.update({"id": c.id, "notification_id": n.id, "week_date": c.week_date.isoformat(),
                     "published_at": c.published_at.isoformat()})
        out.append(data)
    return envelope(True, "", out)


@router.get("/api/campaigns/{campaign_id}")
async def campaign_detail(campaign_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    row = (await db.execute(select(Campaign, Notification, NotificationRecipient.read_at)
             .join(Notification, Notification.campaign_id == Campaign.id)
             .outerjoin(NotificationRecipient, (NotificationRecipient.notification_id == Notification.id)
                        & (NotificationRecipient.user_id == user.id))
             .where(Campaign.id == campaign_id, Campaign.status == "published"))).first()
    if row is None:
        raise HTTPException(404, "err.not_found")
    c, n, read_at = row
    data = core.notification_public(n, read_at)
    data.update({"id": c.id, "notification_id": n.id, "week_date": c.week_date.isoformat(),
                 "published_at": c.published_at.isoformat()})
    return envelope(True, "", data)


@router.get("/api/admin/campaigns")
async def admin_campaigns(request: Request, db: AsyncSession = Depends(get_db)):
    await require_cap(request, db, "campaign/manage")
    rows = (await db.execute(select(Campaign).order_by(Campaign.week_date.desc()).limit(100))).scalars().all()
    return envelope(True, "", [{"id": c.id, "week_date": c.week_date.isoformat(), "title": c.title,
        "body": c.body, "status": c.status, "publish_at": c.publish_at.isoformat(),
        "published_at": c.published_at.isoformat() if c.published_at else ""} for c in rows])


@router.post("/api/admin/campaigns")
async def create_campaign(body: CampaignIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "campaign/manage")
    await check_csrf(request, sess)
    row = await core.save_campaign(db, user, body.model_dump(), ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.created", {"id": row.id})


@router.post("/api/admin/campaigns/{campaign_id}")
async def update_campaign(campaign_id: int, body: CampaignIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "campaign/manage")
    await check_csrf(request, sess)
    row = await core.save_campaign(db, user, body.model_dump(), campaign_id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated", {"id": row.id})


@router.post("/api/admin/campaigns/{campaign_id}/publish")
async def publish_campaign(campaign_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "campaign/manage")
    await check_csrf(request, sess)
    row = (await db.execute(select(Campaign).where(Campaign.id == campaign_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    if utcnow() < row.publish_at:
        raise HTTPException(409, "campaign.too_early")
    n, count = await core.publish_campaign(db, row, user.id)
    await db.commit()
    return envelope(True, "campaign.published", {"recipients": count})


@router.post("/api/admin/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "campaign/manage")
    await check_csrf(request, sess)
    row = (await db.execute(select(Campaign).where(Campaign.id == campaign_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    if row.status != "scheduled":
        raise HTTPException(409, "campaign.not_editable")
    row.status = "cancelled"
    await audit(db, action="campaign.cancelled", actor=user, entity_type="campaign", entity_id=row.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.updated")


@router.get("/api/notifications/push/key")
async def push_key(request: Request, db: AsyncSession = Depends(get_db)):
    await require_user(request, db)
    public, _ = core.vapid_keys()
    return envelope(True, "", {"public_key": public})


@router.post("/api/notifications/push/subscribe")
async def subscribe(body: PushIn, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    core.validate_subscription(body.endpoint, body.p256dh, body.auth)
    # Serialise the per-user device cap. A browser endpoint is a bearer secret:
    # when the same device signs into another account, transfer it instead of
    # leaving push delivery attached to the previous person on a shared device.
    await db.execute(select(func.pg_advisory_xact_lock(func.hashtext("push-user:" + str(user.id)))))
    row = (await db.execute(select(PushSubscription).where(
        PushSubscription.endpoint == body.endpoint).with_for_update())).scalar_one_or_none()
    count = (await db.execute(select(func.count(PushSubscription.id)).where(
        PushSubscription.user_id == user.id, PushSubscription.endpoint != body.endpoint))).scalar_one()
    if row is not None and row.user_id == user.id:
        count += 1
    if count >= core.MAX_PUSH_DEVICES:
        raise HTTPException(409, "notif.push_limit")
    if row is None:
        row = PushSubscription(endpoint=body.endpoint)
        db.add(row)
    row.user_id, row.p256dh, row.auth, row.user_agent = user.id, body.p256dh, body.auth, user_agent(request)
    row.failure_count = 0
    await db.flush()
    await audit(db, action="notif.push_subscribed", actor=user, entity_type="push_subscription", entity_id=row.id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "notif.push_enabled", {"id": row.id})


@router.delete("/api/notifications/push/{subscription_id}")
async def unsubscribe(subscription_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_user(request, db)
    await check_csrf(request, sess)
    row = (await db.execute(select(PushSubscription).where(PushSubscription.id == subscription_id,
                PushSubscription.user_id == user.id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "err.not_found")
    await db.delete(row)
    await audit(db, action="notif.push_unsubscribed", actor=user, entity_type="push_subscription",
                entity_id=subscription_id, ip=client_ip(request))
    await db.commit()
    return envelope(True, "ok.deleted")
