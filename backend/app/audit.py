"""Écriture du journal d'audit (NF-05, 9.2 étape 7). Chaque action métier y écrit une ligne."""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.models import AuditLog

_SKIP = {"created_at", "updated_at"}


def _json_safe(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


def snapshot(obj: Any) -> dict[str, Any]:
    """Copie JSON des colonnes d'une entité (hors horodatages techniques)."""
    mapper = inspect(obj).mapper
    return {c.key: _json_safe(getattr(obj, c.key)) for c in mapper.column_attrs if c.key not in _SKIP}


def record(
    session: Session,
    actor: str,
    action: str,
    entity: Any,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            entity_type=entity.__tablename__,
            entity_id=entity.id,
            before=before,
            after=after,
        )
    )
