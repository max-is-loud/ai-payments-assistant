"""Escalations as resources: list pending, approve one."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_owner
from app.db import audit, escalations
from app.db.engine import session_scope
from app.domain.periods import local_timezone
from app.services.escalations import approve_and_notify

router = APIRouter(prefix="/api/escalations", dependencies=[Depends(require_owner)])


@router.get("")
def pending(request: Request) -> list[dict[str, Any]]:
    """Everything waiting for the owner."""
    with session_scope(request.app.state.services.engine) as session:
        return [
            {
                "id": r.id, "customer_name": r.customer_name, "invoice_id": r.invoice_id,
                "amount_cents": r.amount_cents, "reason": r.reason,
                "created_at": r.created_at.isoformat(),
            }
            for r in escalations.pending(session)
        ]


@router.post("/{escalation_id}/approve")
def approve(escalation_id: str, request: Request) -> dict[str, Any]:
    """Approve from the panel; the click is the confirmation."""
    services = request.app.state.services
    with session_scope(services.engine) as session:
        outcome = approve_and_notify(
            session, escalation_id, gateway=services.gateway, notify=services.notify,
            now=datetime.now(local_timezone()),
        )
        if not outcome.already_approved:
            audit.record(
                session, channel="web", actor="owner", prompt="(escalations panel)",
                action="approve_escalation", parameters={"escalation_id": escalation_id},
                result=outcome.__dict__, mutation=True,
            )
        return outcome.__dict__.copy()
