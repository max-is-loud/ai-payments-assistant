"""Read the audit log."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.auth import require_owner
from app.db import audit
from app.db.engine import session_scope

router = APIRouter(prefix="/api/audit", dependencies=[Depends(require_owner)])


@router.get("")
def recent(request: Request, limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    """Newest first: who asked what, which action ran, and what came back."""
    with session_scope(request.app.state.services.engine) as session:
        return [
            {
                "id": r.id, "created_at": r.created_at.isoformat(), "channel": r.channel,
                "actor": r.actor, "prompt": r.prompt, "action": r.action,
                "parameters": json.loads(r.parameters_json),
                "result": json.loads(r.result_json), "mutation": r.mutation,
            }
            for r in audit.recent(session, limit)
        ]
