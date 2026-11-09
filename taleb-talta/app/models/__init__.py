"""Taleb Talta data model — Wave 0 (foundation).

PostgreSQL, timezone-aware UTC (TIMESTAMPTZ) everywhere — one clock, no
PHP-vs-MySQL timezone trap. ENUMs are declared with an explicit allowed-values
list (ENUMS below) so the DB rejects out-of-range writes (CHECK constraint) and
check_enum_values can verify every literal written from Python.

FK ordering is handled by SQLAlchemy's topological sort of metadata.create_all,
so a referencing table is always created after its target (no errno-150 analogue).
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (String, Integer, BigInteger, Boolean, DateTime, Text, Float,
                        ForeignKey, Enum as SAEnum, UniqueConstraint, Index, JSON, Date, text)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Documented allowed values for every ENUM column (check_enum_values reads this).
ENUMS = {
    "user_role": ["owner", "admin", "moderator", "teacher", "student", "parent"],
    "user_status": ["active", "banned", "suspended", "pending"],
    "audit_severity": ["info", "notice", "warning", "critical"],
    "cap_permission": ["allow", "prevent", "prohibit"],
    "plugin_status": ["present", "installed", "enabled", "disabled"],
    "plugin_type": ["block", "tool", "report", "local", "qtype", "theme",
                    "filter", "auth", "enrol", "repository", "aiprovider"],
    "reset_status": ["pending", "used", "expired"],
    "course_visibility": ["visible", "hidden"],
    "lesson_item_type": ["text", "file", "link", "question"],
    "library_status": ["pending", "approved", "rejected"],
    "enrol_method": ["division", "self", "manual", "purchase"],
    "question_type": ["mcq_single", "mcq_multi", "truefalse", "short", "match", "numeric"],
    "attempt_status": ["in_progress", "submitted", "graded"],
    "channel_kind": ["private", "group", "division", "live"],
    "attachment_purpose": ["chat", "sticker"],
    "sticker_status": ["pending", "approved", "rejected"],
    "report_entity": ["forum_post", "chat_message", "question_post", "sticker"],
    "report_status": ["pending", "resolved", "dismissed"],
    "moderation_decision": ["approve", "remove", "warn", "ban"],
    "restriction_scope": ["chat_evaluations", "all"],
    "field_entity": ["user", "course"],
    "field_type": ["text", "number", "select", "checkbox"],
    "task_status": ["running", "success", "failed", "skipped"],
    "backup_status": ["creating", "ready", "failed"],
    "theme_density": ["comfortable", "compact"],
    "purchase_status": ["pending", "confirmed", "rejected", "cancelled"],
    "notification_kind": ["targeted", "campaign", "purchase", "system"],
    "campaign_status": ["scheduled", "published", "cancelled"],
    "stream_status": ["scheduled", "live", "ended", "cancelled"],
    "push_status": ["pending", "sent", "failed", "skipped"],
}

def _enum(name: str):
    return SAEnum(*ENUMS[name], name=name, native_enum=False,
                  validate_strings=True, create_constraint=True)

class Division(Base):
    __tablename__ = "divisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(160))
    guardian_phone: Mapped[str] = mapped_column(String(20))
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True)
    role: Mapped[str] = mapped_column(_enum("user_role"), default="student")
    status: Mapped[str] = mapped_column(_enum("user_status"), default="active")
    title: Mapped[str] = mapped_column(String(120), default="")
    badge: Mapped[str] = mapped_column(String(120), default="")
    photo_path: Mapped[str] = mapped_column(String(255), default="")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    banned_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # sha256(token)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sesskey: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    absolute_expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(_enum("reset_status"), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PasswordHistory(Base):
    __tablename__ = "password_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_role: Mapped[str] = mapped_column(String(20), default="")
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    severity: Mapped[str] = mapped_column(_enum("audit_severity"), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class RoleCapability(Base):
    __tablename__ = "role_capabilities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    capability: Mapped[str] = mapped_column(String(120))
    permission: Mapped[str] = mapped_column(_enum("cap_permission"), default="allow")
    __table_args__ = (UniqueConstraint("role", "capability", name="uq_role_cap"),)

class UserCapabilityOverride(Base):
    __tablename__ = "user_capability_overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    capability: Mapped[str] = mapped_column(String(120))
    permission: Mapped[str] = mapped_column(_enum("cap_permission"))
    __table_args__ = (UniqueConstraint("user_id", "capability", name="uq_user_cap"),)

class Plugin(Base):
    __tablename__ = "plugins"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(_enum("plugin_type"))
    name: Mapped[str] = mapped_column(String(80))
    component: Mapped[str] = mapped_column(String(120), unique=True)
    disk_version: Mapped[int] = mapped_column(Integer, default=0)
    installed_version: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(_enum("plugin_status"), default="present")
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("type", "name", name="uq_plugin_type_name"),)

class PluginSetting(Base):
    __tablename__ = "plugin_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[int] = mapped_column(ForeignKey("plugins.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("plugin_id", "name", name="uq_plugin_setting"),)

class SiteSetting(Base):
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

class PluginEvent(Base):
    __tablename__ = "plugin_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[int] = mapped_column(ForeignKey("plugins.id"), index=True)
    event: Mapped[str] = mapped_column(String(120))
    observer: Mapped[str] = mapped_column(String(255))

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plugin_id: Mapped[int | None] = mapped_column(ForeignKey("plugins.id"), nullable=True)
    classname: Mapped[str] = mapped_column(String(255), unique=True)
    minute: Mapped[str] = mapped_column(String(20), default="*")
    hour: Mapped[str] = mapped_column(String(20), default="*")
    day: Mapped[str] = mapped_column(String(20), default="*")
    dayofweek: Mapped[str] = mapped_column(String(20), default="*")
    month: Mapped[str] = mapped_column(String(20), default="*")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_token: Mapped[str] = mapped_column(String(64), default="")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label_key: Mapped[str] = mapped_column(String(120), default="")
    label: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(255))
    icon: Mapped[str] = mapped_column(String(60), default="")
    role: Mapped[str] = mapped_column(String(20), default="")   # empty = all roles
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    plugin_id: Mapped[int | None] = mapped_column(ForeignKey("plugins.id"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class RateLimit(Base):
    __tablename__ = "rate_limits"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    key: Mapped[str] = mapped_column(String(160), index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# ===========================================================================
# Wave 1 — Courses, lessons, library
# ===========================================================================

class CourseCategory(Base):
    __tablename__ = "course_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("course_categories.id"), nullable=True)
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True)  # None = all
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    visibility: Mapped[str] = mapped_column(_enum("course_visibility"), default="visible")
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)   # Wave 5 payments; 0 = free
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CourseSection(Base):
    __tablename__ = "course_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("course_sections.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LessonItem(Base):
    __tablename__ = "lesson_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    item_type: Mapped[str] = mapped_column(_enum("lesson_item_type"), default="text")
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")          # text content / question prompt
    url: Mapped[str] = mapped_column(String(500), default="")    # link item
    file_path: Mapped[str] = mapped_column(String(255), default="")  # storage key (file item)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)  # question options
    correct_index: Mapped[int | None] = mapped_column(Integer, nullable=True)  # server-only answer
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("lesson_items.id"), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_progress_user_item"),)

class CourseStudent(Base):
    __tablename__ = "course_students"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    method: Mapped[str] = mapped_column(_enum("enrol_method"), default="self")
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_student"),)

class LibraryItem(Base):
    __tablename__ = "library_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(120), default="")
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True)
    file_path: Mapped[str] = mapped_column(String(255))
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(_enum("library_status"), default="pending", index=True)
    review_reason: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class UserLibrary(Base):
    __tablename__ = "user_library"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    library_item_id: Mapped[int] = mapped_column(ForeignKey("library_items.id"), index=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "library_item_id", name="uq_user_library"),)

# ---- Wave 2: exams & grading ---------------------------------------------
class Question(Base):
    """Question bank item. answer_json is SERVER-ONLY — never serialised to the
    browser before submission. options_json holds the visible choices/pairs."""
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    qtype: Mapped[str] = mapped_column(_enum("question_type"), default="mcq_single")
    prompt: Mapped[str] = mapped_column(Text)
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    answer_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # server-only
    explanation: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    time_limit_minutes: Mapped[int] = mapped_column(Integer, default=0)     # 0 = untimed
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)           # 0 = unlimited
    visibility: Mapped[str] = mapped_column(_enum("course_visibility"), default="visible")
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shuffle: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("exam_id", "question_id", name="uq_exam_question"),)

class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(_enum("attempt_status"), default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    graded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("exam_id", "user_id", "attempt_number",
                                       name="uq_attempt_number"),)

class AttemptAnswer(Base):
    __tablename__ = "attempt_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("exam_attempts.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = pending manual
    points_awarded: Mapped[float] = mapped_column(Float, default=0)
    needs_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("attempt_id", "question_id", name="uq_attempt_answer"),)

class QuestionPost(Base):
    """Per-question discussion thread (exam result review, prompt §6 Wave 2)."""
    __tablename__ = "question_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

# ---- Wave 3: communication + moderation ----------------------------------
class DiscussionThread(Base):
    __tablename__ = "discussion_threads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True, unique=True)
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DiscussionPost(Base):
    __tablename__ = "discussion_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("discussion_threads.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("discussion_posts.id"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    was_filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ForumSubscription(Base):
    __tablename__ = "forum_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("discussion_threads.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    last_seen_post_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("thread_id", "user_id", name="uq_forum_subscription"),)

class Channel(Base):
    __tablename__ = "channels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(_enum("channel_kind"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("uq_division_channel", "division_id", unique=True,
                            postgresql_where=division_id.isnot(None)),)

class ChannelMember(Base):
    __tablename__ = "channel_members"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    last_read_message_id: Mapped[int] = mapped_column(Integer, default=0)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("channel_id", "user_id", name="uq_channel_member"),)

class DirectContact(Base):
    __tablename__ = "direct_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "contact_id", name="uq_direct_contact"),)

class MessageBlock(Base):
    __tablename__ = "message_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    blocked_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_message_block"),)

class Attachment(Base):
    """Opaque storage key; access is always checked against the parent message."""
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(_enum("attachment_purpose"), default="chat")
    file_path: Mapped[str] = mapped_column(String(255), unique=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    mime: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), index=True)
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    attachment_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"), nullable=True, unique=True)
    sticker_id: Mapped[int | None] = mapped_column(ForeignKey("stickers.id"), nullable=True)
    was_filtered: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_chat_channel_id_cursor", "channel_id", "id"),)

class Sticker(Base):
    __tablename__ = "stickers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachments.id"), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(_enum("sticker_status"), default="pending", index=True)
    review_reason: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ProfanityWord(Base):
    __tablename__ = "profanity_words"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(120), unique=True)  # normalised, never public
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ContentReport(Base):
    __tablename__ = "content_reports"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(_enum("report_entity"))
    entity_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(_enum("report_status"), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("reporter_id", "target_type", "entity_id", name="uq_content_report"),)

class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("content_reports.id"), nullable=True)
    decision: Mapped[str] = mapped_column(_enum("moderation_decision"))
    reason: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class ModerationStrike(Base):
    __tablename__ = "moderation_strikes"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class UserRestriction(Base):
    """Scoped bans leave course access intact. Full-site bans use User.status."""
    __tablename__ = "user_restrictions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    scope: Mapped[str] = mapped_column(_enum("restriction_scope"), default="chat_evaluations")
    reason: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---- Wave 4: administration, builders, reports and cron -------------------
class CustomField(Base):
    __tablename__ = "custom_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    applies_to: Mapped[str] = mapped_column(_enum("field_entity"), index=True)
    machine_name: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    field_type: Mapped[str] = mapped_column(_enum("field_type"), default="text")
    options_json: Mapped[list] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("applies_to", "machine_name", name="uq_custom_field_name"),)

class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("custom_fields.id"), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    value_text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("field_id", "entity_id", name="uq_custom_field_value"),)

class DashboardBlock(Base):
    __tablename__ = "dashboard_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(_enum("user_role"))
    block_key: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("role", "block_key", name="uq_dashboard_block"),)

class DashboardPreference(Base):
    __tablename__ = "dashboard_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    block_key: Mapped[str] = mapped_column(String(60))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("user_id", "block_key", name="uq_dashboard_preference"),)

class ThemePreset(Base):
    __tablename__ = "theme_presets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_theme: Mapped[str] = mapped_column(String(20), default="light")
    primary_color: Mapped[str] = mapped_column(String(7))
    secondary_color: Mapped[str] = mapped_column(String(7))
    accent_color: Mapped[str] = mapped_column(String(7))
    radius: Mapped[int] = mapped_column(Integer, default=16)
    density: Mapped[str] = mapped_column(_enum("theme_density"), default="comfortable")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class RoleTheme(Base):
    __tablename__ = "role_themes"
    role: Mapped[str] = mapped_column(_enum("user_role"), primary_key=True)
    theme_key: Mapped[str] = mapped_column(String(40))

class TaskRun(Base):
    __tablename__ = "task_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # history survives plugin uninstall
    task_key: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(_enum("task_status"), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_key: Mapped[str] = mapped_column(String(120), default="")
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

class DigestDelivery(Base):
    __tablename__ = "digest_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period_date: Mapped[str] = mapped_column(String(10))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("user_id", "period_date", name="uq_digest_user_day"),)

class BackupArtifact(Base):
    __tablename__ = "backup_artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(120), unique=True)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(_enum("backup_status"), default="creating")
    include_uploads: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error_key: Mapped[str] = mapped_column(String(120), default="")


# ---- Wave 5: manual purchases, notifications, campaigns and live -----------
class Purchase(Base):
    __tablename__ = "purchases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="EGP")
    status: Mapped[str] = mapped_column(_enum("purchase_status"), default="pending", index=True)
    reference: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("uq_purchase_pending_course", "user_id", "course_id", unique=True,
              postgresql_where=text("lesson_id IS NULL AND status = 'pending'")),
        Index("uq_purchase_pending_lesson", "user_id", "lesson_id", unique=True,
              postgresql_where=text("lesson_id IS NOT NULL AND status = 'pending'")),
    )

class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_date: Mapped[datetime] = mapped_column(Date, unique=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(_enum("campaign_status"), default="scheduled", index=True)
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(_enum("notification_kind"), default="targeted", index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(255), default="/notifications")
    audience_role: Mapped[str] = mapped_column(String(20), default="")
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id"), nullable=True, unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

class NotificationRecipient(Base):
    __tablename__ = "notification_recipients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    push_status: Mapped[str] = mapped_column(_enum("push_status"), default="pending", index=True)
    push_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uq_notification_recipient"),)

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class LiveStream(Base):
    __tablename__ = "live_streams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    audience: Mapped[str] = mapped_column(String(20), default="all")  # all / course / division
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True)
    division_id: Mapped[int | None] = mapped_column(ForeignKey("divisions.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(_enum("stream_status"), default="scheduled", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    playback_url: Mapped[str] = mapped_column(Text, default="")
    ingest_url_encrypted: Mapped[str] = mapped_column(Text, default="")
    publish_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    chat_channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"), nullable=True, unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
