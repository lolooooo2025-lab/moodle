"""Text screening, persisted warnings, scoped bans and audited moderation.

The dictionary is editable data, not hard-coded copy. Matching normalises Arabic
presentation forms, diacritics, tatweel and letter variants. A submission with
one or more matches counts as ONE strike, not one strike per word. PostgreSQL's
atomic upsert keeps concurrent submissions from losing a warning.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.dialects.postgresql import insert
from app.core.audit import audit
from app.core import session as sessmgr
from app.models import (User, ProfanityWord, ModerationStrike, ModerationAction,
                        UserRestriction, utcnow)

_TRANSLATION = str.maketrans({
    "\u0622": "\u0627", "\u0623": "\u0627", "\u0625": "\u0627",
    "\u0671": "\u0627", "\u0649": "\u064a", "\u06cc": "\u064a",
    "\u06a9": "\u0643", "\u0629": "\u0647",
})
_AR = re.compile(r"[\u0600-\u06ff]")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().translate(_TRANSLATION)
    text = "".join(c for c in text if unicodedata.category(c) not in ("Mn", "Cf", "Cc")
                   or c in "\n\t")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def _normalised_with_map(text: str) -> tuple[str, list[int]]:
    """Normalise for matching while remembering original character offsets."""
    chars: list[str] = []
    offsets: list[int] = []
    for i, ch in enumerate(text or ""):
        for c in unicodedata.normalize("NFKC", ch).lower().translate(_TRANSLATION):
            if unicodedata.category(c) in ("Mn", "Cf", "Cc") and c not in "\n\t":
                continue
            if c in " \t\r\f\v":
                if chars and chars[-1] == " ":
                    continue
                chars.append(" ")
                offsets.append(i)
            else:
                chars.append(c)
                offsets.append(i)
    return "".join(chars), offsets


def filter_text(text: str, words: list[str]) -> tuple[str, bool]:
    """Mask profanity in-place; preserve the author's casing/diacritics elsewhere."""
    text = text or ""
    cleaned, offsets = _normalised_with_map(text)
    patterns = []
    for word in sorted(set(words), key=len, reverse=True):
        letters = [re.escape(c) + "+" for c in word if not c.isspace()]
        if not letters:
            continue
        body = r"\s*".join(letters)
        if _AR.search(word):
            body = r"(?:\u0627\u0644|\u0648|\u0641|\u0628|\u0644)?" + body
        patterns.append(body)
    if not patterns:
        return text, False
    # Latin terms need word boundaries (do not censor words such as "class").
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(patterns) + r")(?!\w)", re.UNICODE)
    spans = []
    for match in pattern.finditer(cleaned):
        if not match.group():
            continue
        start = offsets[match.start()]
        end = offsets[match.end() - 1] + 1
        spans.append((start, end))
    if not spans:
        return text, False
    spans.sort()
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    out = []
    cursor = 0
    for start, end in merged:
        out.append(text[cursor:start])
        out.append("*" * (end - start))
        cursor = end
    out.append(text[cursor:])
    return "".join(out), True


async def dictionary(db) -> list[str]:
    return list((await db.execute(select(ProfanityWord.word).where(
        ProfanityWord.enabled.is_(True)))).scalars().all())


async def active_restriction(db, user_id: int, scope: str = "chat_evaluations"):
    return (await db.execute(select(UserRestriction).where(
        UserRestriction.user_id == user_id, UserRestriction.revoked_at.is_(None),
        UserRestriction.expires_at > utcnow(),
        or_(UserRestriction.scope == "all", UserRestriction.scope == scope))
        .order_by(UserRestriction.expires_at.desc()))).scalars().first()


async def require_communication(db, user):
    if await active_restriction(db, user.id):
        raise HTTPException(status_code=403, detail="chat.banned_30")


async def require_evaluations(db, user):
    if await active_restriction(db, user.id):
        raise HTTPException(status_code=403, detail="eval.restricted")


async def ban_user(db, target: User, *, actor: User | None, reason: str,
                   report_id: int | None = None, ip: str = "", days: int = 30):
    until = utcnow() + timedelta(days=days)
    restriction = UserRestriction(user_id=target.id, scope="chat_evaluations",
                                  reason=reason[:2000], expires_at=until,
                                  created_by=actor.id if actor else None)
    db.add(restriction)
    db.add(ModerationAction(actor_id=actor.id if actor else target.id,
                            target_user_id=target.id, report_id=report_id,
                            decision="ban", reason=reason[:2000], expires_at=until))
    await sessmgr.revoke_all_for_user(db, target.id)
    await audit(db, action="moderation.banned", actor=actor, actor_id=target.id if actor is None else None,
                entity_type="user", entity_id=target.id, after={"days": days, "scope": "chat_evaluations"},
                ip=ip, severity="critical")
    await db.commit()
    return restriction


@dataclass
class ScreenResult:
    values: dict
    matched: bool
    strikes: int = 0
    message_key: str = ""


async def record_violation(db, user: User, *, source: str, ip: str = "",
                           actor: User | None = None, reason: str = "", report_id: int | None = None) -> ScreenResult:
    stmt = insert(ModerationStrike).values(user_id=user.id, count=1, updated_at=utcnow())
    stmt = stmt.on_conflict_do_update(index_elements=[ModerationStrike.user_id],
                                      set_={"count": ModerationStrike.count + 1, "updated_at": utcnow()})
    count = (await db.execute(stmt.returning(ModerationStrike.count))).scalar_one()
    if actor is not None:
        db.add(ModerationAction(actor_id=actor.id, target_user_id=user.id, report_id=report_id,
                                decision="warn", reason=reason[:2000]))
    await audit(db, action="moderation.warning", actor=actor, actor_id=user.id if actor is None else None,
                entity_type="user", entity_id=user.id,
                after={"count": count, "source": source, "reason": reason[:500]}, ip=ip, severity="warning")
    if count >= 3:
        await ban_user(db, user, actor=actor, reason=reason or source, report_id=report_id, ip=ip)
        return ScreenResult({}, True, count, "chat.banned_30")
    await db.commit()
    return ScreenResult({}, True, count, "chat.warning_first" if count == 1 else "chat.warning_second")


async def screen(db, user: User, fields: dict[str, str], *, source: str,
                 ip: str = "", count_strike: bool = True) -> ScreenResult:
    """Screen BEFORE creating content. Commit warning side effects independently
    so a later validation failure cannot erase the warning."""
    words = await dictionary(db)
    values, matched = {}, False
    for key, value in fields.items():
        values[key], hit = filter_text(value or "", words)
        matched = matched or hit
    if not matched:
        return ScreenResult(values, False)
    if not count_strike:
        return ScreenResult(values, True, message_key="chat.profanity_masked")
    outcome = await record_violation(db, user, source=source, ip=ip)
    if outcome.strikes >= 3:
        raise HTTPException(status_code=403, detail="chat.banned_30")
    outcome.values = values
    return outcome
