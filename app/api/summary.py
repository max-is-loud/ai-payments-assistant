"""The daily summary: facts always, narration on request."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.agent.events import to_jsonable
from app.agent.narrator import narrate_summary
from app.api.auth import require_owner
from app.domain.periods import local_timezone
from app.domain.series import build_series
from app.domain.summary import build_daily_facts

router = APIRouter(prefix="/api/summary", dependencies=[Depends(require_owner)])


@router.get("/today")
def today(request: Request, narrate: bool = True) -> dict[str, Any]:
    """Facts computed in Python; `narrate=false` skips the model for the live rail."""
    services = request.app.state.services
    facts = build_daily_facts(
        services.gateway.list_payments(), services.gateway.list_invoices(status="open"),
        datetime.now(local_timezone()),
    )
    currency = services.gateway.default_currency()
    text = narrate_summary(services.llm, facts, currency) if narrate else None
    return {"facts": to_jsonable(facts), "text": text, "currency": currency.code}


@router.get("/series")
def series(request: Request) -> dict[str, Any]:
    """Per-day, per-hour, and per-customer totals for the charts; never touches the model."""
    services = request.app.state.services
    return to_jsonable(
        build_series(services.gateway.list_payments(), datetime.now(local_timezone()))
    )
