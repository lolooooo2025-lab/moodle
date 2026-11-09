"""Admin-defined fields: fixed data types, validated values, no schema mutation."""
from __future__ import annotations
import math
import re
from sqlalchemy import select
from fastapi import HTTPException
from app.core import moderation
from app.models import CustomField, CustomFieldValue, utcnow


def public(field: CustomField) -> dict:
    return {"id": field.id, "applies_to": field.applies_to, "machine_name": field.machine_name,
            "label": field.label, "field_type": field.field_type, "options": field.options_json,
            "required": field.required, "enabled": field.enabled, "sort_order": field.sort_order}


async def definitions(db, entity: str, *, include_disabled=False):
    q = select(CustomField).where(CustomField.applies_to == entity)
    if not include_disabled:
        q = q.where(CustomField.enabled.is_(True))
    return (await db.execute(q.order_by(CustomField.sort_order, CustomField.id))).scalars().all()


def normalize_value(field: CustomField, value) -> str:
    if field.field_type == "checkbox":
        if isinstance(value, bool):
            return "1" if value else "0"
        if str(value) in ("0", "1", ""):
            return str(value)
        raise HTTPException(422, "err.field_invalid")
    text = str(value if value is not None else "").strip()
    if len(text) > 1000 or any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise HTTPException(422, "err.field_invalid")
    if field.field_type == "number" and text:
        try:
            number = float(text)
        except ValueError:
            raise HTTPException(422, "customfield.number_invalid")
        if not math.isfinite(number) or abs(number) > 1_000_000_000:
            raise HTTPException(422, "customfield.number_invalid")
    if field.field_type == "select" and text and text not in field.options_json:
        raise HTTPException(422, "customfield.option_invalid")
    return text


async def validate_values(db, entity: str, values: dict, *, user=None, count_strike=False) -> dict:
    if not isinstance(values, dict) or len(values) > 50:
        raise HTTPException(422, "err.field_invalid")
    fields = await definitions(db, entity)
    known = {f.machine_name: f for f in fields}
    unknown = set(values) - set(known)
    if unknown:
        raise HTTPException(422, "customfield.unknown")
    result = {}
    for field in fields:
        supplied = field.machine_name in values
        text = normalize_value(field, values.get(field.machine_name, ""))
        if field.required and (not supplied or not text or (field.field_type == "checkbox" and text == "0")):
            raise HTTPException(422, "customfield.required_missing")
        result[field.machine_name] = text
    if user is not None:
        text_fields = {f.machine_name: result[f.machine_name] for f in fields if f.field_type == "text" and result[f.machine_name]}
        if text_fields:
            screened = await moderation.screen(db, user, text_fields, source="custom_field", count_strike=count_strike)
            result.update(screened.values)
    return result


async def save_values(db, entity: str, entity_id: int, cleaned: dict):
    fields = {f.machine_name: f for f in await definitions(db, entity)}
    for name, text in cleaned.items():
        field = fields[name]
        row = (await db.execute(select(CustomFieldValue).where(
            CustomFieldValue.field_id == field.id, CustomFieldValue.entity_id == entity_id))).scalar_one_or_none()
        if row is None:
            row = CustomFieldValue(field_id=field.id, entity_id=entity_id, value_text=text)
            db.add(row)
        else:
            row.value_text = text
            row.updated_at = utcnow()
    await db.flush()


async def get_values(db, entity: str, entity_id: int) -> dict:
    rows = (await db.execute(select(CustomField.machine_name, CustomFieldValue.value_text)
              .join(CustomFieldValue, CustomFieldValue.field_id == CustomField.id)
              .where(CustomField.applies_to == entity, CustomField.enabled.is_(True),
                     CustomFieldValue.entity_id == entity_id))).all()
    return {name: value for name, value in rows}
