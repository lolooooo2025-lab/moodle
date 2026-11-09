"""Scoped operational reports + formula-safe CSV/XLSX exports (Wave 4)."""
from __future__ import annotations
import csv
import io
from datetime import date, datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, func, union_all, literal, exists
from app.models import (Course, CourseSection, Lesson, CourseStudent, User, Division, LoginAttempt, LessonProgress,
                        ExamAttempt, Exam, DiscussionPost, DiscussionThread, AuditLog,
                        CustomField, CustomFieldValue)

MAX_ROWS = 10000
TYPES = ("enrolments", "activity", "grades", "usage", "audit")


def window(date_from: str, date_to: str):
    try:
        start = date.fromisoformat(date_from) if date_from else date.today() - timedelta(days=30)
        end = date.fromisoformat(date_to) if date_to else date.today()
    except ValueError:
        raise HTTPException(422, "report.date_invalid")
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "report.range_invalid")
    return (datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
            datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))


async def scope_courses(db, user) -> list[int] | None:
    if user.role in ("owner", "admin"):
        return None
    if user.role == "teacher":
        return list((await db.execute(select(Course.id).where(Course.teacher_id == user.id))).scalars())
    return []


def _in_scope(column, ids):
    return column.in_(ids) if ids is not None else True


def _custom_exists(entity, entity_column, name, value):
    if not name:
        return True
    return exists(select(CustomFieldValue.id).join(CustomField, CustomField.id == CustomFieldValue.field_id)
                  .where(CustomField.applies_to == entity, CustomField.machine_name == name,
                         CustomField.enabled.is_(True), CustomFieldValue.entity_id == entity_column,
                         CustomFieldValue.value_text == value))


def _iso(value):
    return value.isoformat() if value is not None else ""


async def build(db, user, kind: str, *, date_from="", date_to="", course_id=0,
                division_id=0, custom_field="", custom_value="") -> dict:
    if kind not in TYPES:
        raise HTTPException(404, "report.unknown")
    start, end = window(date_from, date_to)
    ids = await scope_courses(db, user)
    if kind == "audit":
        from app.core.capabilities import tt_can
        if not await tt_can(db, user, "audit/view"):
            raise HTTPException(403, "err.forbidden")
    elif kind in ("enrolments", "grades", "usage") and ids == []:
        raise HTTPException(403, "report.no_courses")
    if course_id:
        if ids is not None and course_id not in ids:
            raise HTTPException(403, "report.course_forbidden")
        if not (await db.execute(select(Course.id).where(Course.id == course_id))).scalar_one_or_none():
            raise HTTPException(404, "err.course_not_found")
    course_filter = Course.id == course_id if course_id else _in_scope(Course.id, ids)
    division_filter = User.division_id == division_id if division_id else True
    filter_entity, filter_name = "", ""
    if kind != "audit" and ":" in custom_field:
        filter_entity, filter_name = custom_field.split(":", 1)
        if filter_entity not in ("user", "course"):
            raise HTTPException(422, "customfield.unknown_entity")
    user_fields = _custom_exists("user", User.id, filter_name, custom_value) if filter_entity == "user" else True
    course_fields = _custom_exists("course", Course.id, filter_name, custom_value) if filter_entity == "course" else True
    columns, rows = [], []
    if kind == "enrolments":
        columns = ["student", "phone", "division", "course", "method", "enrolled_at"]
        result = (await db.execute(select(User.name, User.phone, Division.name, Course.title,
                    CourseStudent.method, CourseStudent.enrolled_at)
                    .join(CourseStudent, CourseStudent.user_id == User.id)
                    .join(Course, Course.id == CourseStudent.course_id)
                    .outerjoin(Division, Division.id == User.division_id)
                    .where(CourseStudent.enrolled_at >= start, CourseStudent.enrolled_at < end,
                           course_filter, division_filter, user_fields, course_fields)
                    .order_by(CourseStudent.enrolled_at.desc()).limit(MAX_ROWS + 1))).all()
        rows = [[r[0], r[1], r[2] or "", r[3], r[4], _iso(r[5])] for r in result]
    elif kind == "grades":
        columns = ["student", "phone", "course", "exam", "score", "max_score", "percent", "submitted_at"]
        best = (select(ExamAttempt.exam_id, ExamAttempt.user_id, ExamAttempt.score,
                       ExamAttempt.max_score, ExamAttempt.submitted_at)
                .where(ExamAttempt.status == "graded", ExamAttempt.submitted_at >= start,
                       ExamAttempt.submitted_at < end)
                .distinct(ExamAttempt.exam_id, ExamAttempt.user_id)
                .order_by(ExamAttempt.exam_id, ExamAttempt.user_id,
                          ExamAttempt.score.desc(), ExamAttempt.submitted_at.desc()).subquery())
        result = (await db.execute(select(User.name, User.phone, Course.title, Exam.title,
                    best.c.score, best.c.max_score, best.c.submitted_at)
                    .join(best, best.c.user_id == User.id)
                    .join(Exam, Exam.id == best.c.exam_id)
                    .join(Course, Course.id == Exam.course_id)
                    .where(course_filter, division_filter, user_fields, course_fields)
                    .order_by(Course.title, User.name).limit(MAX_ROWS + 1))).all()
        rows = [[r[0], r[1], r[2], r[3], r[4], r[5],
                 round(100 * r[4] / r[5], 2) if r[5] else 0, _iso(r[6])] for r in result]
    elif kind == "usage":
        columns = ["student", "phone", "division", "active_days", "completions", "submitted_exams"]
        login_day = func.distinct(func.date(LoginAttempt.created_at))
        logins = (select(func.count(login_day))
                  .where(LoginAttempt.phone == User.phone, LoginAttempt.success.is_(True),
                         LoginAttempt.created_at >= start, LoginAttempt.created_at < end)
                  .scalar_subquery())
        completions = (select(func.count(LessonProgress.id))
                       .join(Lesson, Lesson.id == LessonProgress.lesson_id)
                       .join(CourseSection, CourseSection.id == Lesson.section_id)
                       .join(Course, Course.id == CourseSection.course_id)
                       .where(LessonProgress.user_id == User.id, LessonProgress.completed_at >= start,
                              LessonProgress.completed_at < end, course_filter)).scalar_subquery()
        attempts = (select(func.count(ExamAttempt.id)).join(Exam, Exam.id == ExamAttempt.exam_id)
                    .join(Course, Course.id == Exam.course_id)
                    .where(ExamAttempt.user_id == User.id, ExamAttempt.submitted_at >= start,
                           ExamAttempt.submitted_at < end, course_filter)).scalar_subquery()
        result = (await db.execute(select(User.name, User.phone, Division.name,
                    logins, completions, attempts).outerjoin(Division, Division.id == User.division_id)
                    .where(User.status == "active", division_filter, user_fields, course_fields,
                           exists(select(CourseStudent.id).join(Course, Course.id == CourseStudent.course_id)
                                  .where(CourseStudent.user_id == User.id, course_filter)))
                    .order_by(User.name).limit(MAX_ROWS + 1))).all()
        rows = [list(r) for r in result]
    elif kind == "activity":
        columns = ["day", "metric", "count"]
        day = func.date(LoginAttempt.created_at).label("day")
        parts = [select(day, literal("logins").label("metric"), func.count(LoginAttempt.id).label("count"))
                 .join(User, User.phone == LoginAttempt.phone)
                 .where(LoginAttempt.success.is_(True), LoginAttempt.created_at >= start,
                        LoginAttempt.created_at < end, division_filter, user_fields)
                 .group_by(day)]
        parts.append(select(func.date(CourseStudent.enrolled_at), literal("enrolments"), func.count(CourseStudent.id))
                     .join(User, User.id == CourseStudent.user_id).join(Course, Course.id == CourseStudent.course_id)
                     .where(CourseStudent.enrolled_at >= start, CourseStudent.enrolled_at < end,
                            course_filter, division_filter, user_fields, course_fields)
                     .group_by(func.date(CourseStudent.enrolled_at)))
        parts.append(select(func.date(ExamAttempt.submitted_at), literal("exam_submissions"), func.count(ExamAttempt.id))
                     .join(User, User.id == ExamAttempt.user_id).join(Exam, Exam.id == ExamAttempt.exam_id)
                     .join(Course, Course.id == Exam.course_id)
                     .where(ExamAttempt.submitted_at >= start, ExamAttempt.submitted_at < end,
                            course_filter, division_filter, user_fields, course_fields)
                     .group_by(func.date(ExamAttempt.submitted_at)))
        parts.append(select(func.date(DiscussionPost.created_at), literal("forum_posts"), func.count(DiscussionPost.id))
                     .join(User, User.id == DiscussionPost.user_id)
                     .join(DiscussionThread, DiscussionThread.id == DiscussionPost.thread_id)
                     .where(DiscussionPost.created_at >= start, DiscussionPost.created_at < end,
                            DiscussionPost.deleted_at.is_(None), division_filter, user_fields,
                            DiscussionThread.course_id.in_(select(Course.id).where(course_filter, course_fields)))
                     .group_by(func.date(DiscussionPost.created_at)))
        combined = union_all(*parts).subquery()
        result = (await db.execute(select(combined).order_by(combined.c.day.desc(), combined.c.metric)
                    .limit(MAX_ROWS + 1))).all()
        rows = [[str(r[0]), r[1], r[2]] for r in result]
    else:
        columns = ["id", "actor_id", "actor_role", "action", "entity_type", "entity_id", "severity", "ip", "created_at"]
        result = (await db.execute(select(AuditLog).where(AuditLog.created_at >= start,
                    AuditLog.created_at < end, AuditLog.action == custom_field if custom_field else True)
                    .order_by(AuditLog.created_at.desc()).limit(MAX_ROWS + 1))).scalars().all()
        rows = [[r.id, r.actor_id or "", r.actor_role, r.action, r.entity_type, r.entity_id,
                 r.severity, r.ip, _iso(r.created_at)] for r in result]
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]
    return {"kind": kind, "columns": columns, "rows": rows, "total": len(rows),
            "truncated": truncated, "from": start.date().isoformat(), "to": (end - timedelta(days=1)).date().isoformat()}


def safe_cell(value):
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


def to_csv(report: dict) -> bytes:
    from app.core.i18n import t
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow([t("report.column." + c) for c in report["columns"]])
    for row in report["rows"]:
        writer.writerow([safe_cell(v) for v in row])
    return buf.getvalue().encode("utf-8-sig")


def to_xlsx(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    from app.core.i18n import t
    wb = Workbook()
    ws = wb.active
    ws.title = t("report." + report["kind"])[:31]
    ws.sheet_view.rightToLeft = True
    ws.append([t("report.column." + c) for c in report["columns"]])
    for row in report["rows"]:
        ws.append([safe_cell(str(v)[:32767]) if isinstance(v, str) else safe_cell(v) for v in row])
    for cell in ws[1]:
        cell.font = Font(name="Cairo", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0848A4")
        cell.alignment = Alignment(horizontal="right")
    for index in range(1, len(report["columns"]) + 1):
        ws.column_dimensions[get_column_letter(index)].width = 24
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
