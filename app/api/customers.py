"""Owner-side control over customer Telegram bindings."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_owner
from app.db import bindings
from app.db.engine import session_scope

router = APIRouter(prefix="/api/customers", dependencies=[Depends(require_owner)])


@router.delete("/{customer_id}/telegram-binding")
def revoke(customer_id: str, request: Request) -> dict[str, int]:
    """Revoke every active binding for a customer."""
    with session_scope(request.app.state.services.engine) as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        return {"revoked": bindings.revoke_for_customer(session, customer_id, now)}
