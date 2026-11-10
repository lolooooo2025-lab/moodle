"""Report viewing/export API. Every export is scoped, rate-limited and audited."""
from __future__ import annotations
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core import reports, customfields, ratelimit
from app.core.audit import audit
from app.api.deps import envelope, require_cap, client_ip
from app.models import Course, Division

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/meta")
async def meta(request: Request, db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "report/view")
    ids = await reports.scope_courses(db, user)
    query = select(Course.id, Course.title).where(Course.deleted_at.is_(None))
    if ids is not None:
        query = query.where(Course.id.in_(ids))
    courses = (await db.execute(query.order_by(Course.title))).all()
    divisions = (await db.execute(select(Division.id, Division.name).order_by(Division.name))).all()
    fields = {"user": [customfields.public(f) for f in await customfields.definitions(db, "user")],
              "course": [customfields.public(f) for f in await customfields.definitions(db, "course")]}
    allowed = [k for k in reports.TYPES if k != "audit" or user.role in ("owner", "admin")]
    if ids == []:
        allowed = [k for k in allowed if k == "activity"]
    return envelope(True, "", {"courses": [{"id": c.id, "title": c.title} for c in courses],
                               "divisions": [{"id": d.id, "name": d.name} for d in divisions],
                               "fields": fields, "types": allowed})


@router.get("/{kind}")
async def view(kind: str, request: Request, date_from: str = "", date_to: str = "",
               course_id: int = 0, division_id: int = 0, custom_field: str = "", custom_value: str = "",
               db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "report/view")
    data = await reports.build(db, user, kind, date_from=date_from, date_to=date_to,
                               course_id=course_id, division_id=division_id,
                               custom_field=custom_field, custom_value=custom_value)
    return envelope(True, "", data)


@router.get("/{kind}/export/{fmt}")
async def export(kind: str, fmt: str, request: Request, date_from: str = "", date_to: str = "",
                 course_id: int = 0, division_id: int = 0, custom_field: str = "", custom_value: str = "",
                 db: AsyncSession = Depends(get_db)):
    sess, user = await require_cap(request, db, "report/view")
    if fmt not in ("csv", "xlsx"):
        raise HTTPException(404, "report.format_unknown")
    if not await ratelimit.hit(db, f"report_export:{user.id}", limit=60, window=3600):
        raise HTTPException(429, "err.rate_limited")
    data = await reports.build(db, user, kind, date_from=date_from, date_to=date_to,
                               course_id=course_id, division_id=division_id,
                               custom_field=custom_field, custom_value=custom_value)
    await audit(db, action="report.exported", actor=user, entity_type="report", entity_id=kind,
                after={"format": fmt, "rows": data["total"], "from": data["from"], "to": data["to"]},
                ip=client_ip(request), severity="notice")
    await db.commit()
    content = reports.to_csv(data) if fmt == "csv" else reports.to_xlsx(data)
    media = "text/csv; charset=utf-8" if fmt == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{kind}-{data["from"]}-{data["to"]}.{fmt}"'})
