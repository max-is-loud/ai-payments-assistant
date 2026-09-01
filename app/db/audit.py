"""The audit log: every executed action and the prompt behind it."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.clock import utcnow
from app.db.models import AuditEntry


def record(
    session: Session,
    *,
    channel: str,
    actor: str,
    prompt: str,
    action: str,
    parameters: dict[str, Any],
    result: Any,
    mutation: bool,
) -> AuditEntry:
    """Append one entry. Results are serialised with `default=str` so datetimes survive."""
    row = AuditEntry(
        created_at=utcnow(), channel=channel, actor=actor, prompt=prompt, action=action,
        parameters_json=json.dumps(parameters, default=str),
        result_json=json.dumps(result, default=str), mutation=mutation,
    )
    session.add(row)
    session.flush()
    return row


def recent(session: Session, limit: int = 100) -> list[AuditEntry]:
    """Newest first for the API."""
    return list(session.scalars(
        select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    ).all())
