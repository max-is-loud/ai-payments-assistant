"""Conversational routes: send a turn, confirm or cancel a proposal, read history."""

import json
import logging
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.actions.context import OwnerContext
from app.actions.owner_registry import build_owner_registry
from app.agent.confirm import (
    AlreadyDecided,
    ConfirmationError,
    InProgress,
    NeedsReview,
    UnknownAction,
    execute_pending,
    recover_executing,
)
from app.agent.events import AgentEvent
from app.agent.loop import TurnHooks, run_turn
from app.agent.narrator import narrate_result
from app.agent.prompts import web_planner_system
from app.api.auth import require_owner
from app.api.sse import sse_response
from app.db import audit, conversations, pending_actions
from app.db.engine import session_scope
from app.domain.periods import local_timezone
from app.llm.base import ChatMessage, LLMError
from app.stripe_.gateway import StripeGatewayError

if TYPE_CHECKING:
    from app.api.app import Services

router = APIRouter(prefix="/api/conversations", dependencies=[Depends(require_owner)])
OWNER_REGISTRY = build_owner_registry()
CHANNEL, ACTOR = "web", "owner"

log = logging.getLogger(__name__)


def _done(summary: str) -> str:
    """The transcript line when no narrator ran: the summary the owner approved."""
    return f"Done: {summary}."


def _owner_ctx(services: "Services", session: Session) -> OwnerContext:
    """Owner context over the process services, outside a request."""
    return OwnerContext(
        gateway=services.gateway, session=session, now=datetime.now(local_timezone()),
        notify=services.notify,
    )


def recover_interrupted(services: "Services") -> list[str]:
    """Finish web-channel executions a previous API process died in the middle of.

    Runs once at startup. Each row inside the recovery window is re-driven
    with its stored parameters and idempotency key, so Stripe replays whatever
    it already did rather than doing it again; the transcript gets the plain
    "Done" line, since no narration is worth a model call the owner is not
    waiting for. A row past the window is parked for a manual check and the
    transcript says so. A failure on one row is logged and marks that row
    failed; it never stops the API.

    Returns:
        The ids that were finished.
    """
    with session_scope(services.engine) as session:
        interrupted = [
            (row.id, row.conversation_id) for row in pending_actions.executing(session, CHANNEL)
        ]
    recovered: list[str] = []
    for action_id, conversation_id in interrupted:
        try:
            with session_scope(services.engine) as session:
                try:
                    execution = recover_executing(
                        session=session, action_id=action_id, registry=OWNER_REGISTRY,
                        ctx=_owner_ctx(services, session),
                    )
                except NeedsReview as exc:
                    conversations.append(session, conversation_id, "assistant", str(exc))
                    log.error("%s", exc)
                    continue
                conversations.append(
                    session, conversation_id, "assistant", _done(execution.summary)
                )
            recovered.append(action_id)
            log.warning("Recovered interrupted execution %s", action_id)
        except Exception:  # noqa: BLE001 — one bad row must not stop startup
            log.exception("Could not recover interrupted execution %s", action_id)
    return recovered


class MessageIn(BaseModel):
    """A user turn."""

    text: str = Field(..., min_length=1, max_length=2000)


class ActionRef(BaseModel):
    """Reference to a pending action."""

    action_id: str


def _ctx(request: Request, session: Session) -> OwnerContext:
    """Owner context over the process services."""
    return _owner_ctx(request.app.state.services, session)


def _hooks(session: Session, conversation_id: str, prompt: str) -> TurnHooks:
    """DB-backed hooks that commit right away so the write lock is never held across an LLM call."""
    def propose(spec: Any, params: Any, summary: str) -> str:
        """Store the proposal."""
        row = pending_actions.create(
            session, conversation_id=conversation_id, channel=CHANNEL, actor=ACTOR,
            action=spec.name, parameters=params.model_dump(mode="json"), summary=summary,
            prompt=prompt,
        )
        session.commit()
        return row.id

    def record(action: str, parameters: dict[str, Any], result: Any, mutation: bool) -> None:
        """Audit an executed read."""
        audit.record(
            session, channel=CHANNEL, actor=ACTOR, prompt=prompt, action=action,
            parameters=parameters, result=result, mutation=mutation,
        )
        session.commit()

    return TurnHooks(propose=propose, audit=record)


@router.post("/{conversation_id}/messages")
def post_message(conversation_id: str, body: MessageIn, request: Request) -> Any:
    """Run one agent turn and stream its events."""
    services = request.app.state.services

    def events() -> Iterator[AgentEvent]:
        """Persist the user turn, run the loop, persist the assistant's terminal message."""
        with session_scope(services.engine) as session:
            conversations.ensure(session, conversation_id, CHANNEL)
            history = [
                ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
                for m in conversations.history(session, conversation_id)
            ]
            conversations.append(session, conversation_id, "user", body.text)
            session.commit()
            ctx = _ctx(request, session)
            system = web_planner_system(
                registry=OWNER_REGISTRY, today=ctx.now.date(),
                currency=ctx.gateway.default_currency(),
            )
            hooks = _hooks(session, conversation_id, body.text)
            try:
                for event in run_turn(
                    llm=services.llm, registry=OWNER_REGISTRY, ctx=ctx, system=system,
                    history=history, prompt=body.text, hooks=hooks,
                ):
                    if event.type in ("answer", "clarify"):
                        text = event.data.get("text") or event.data.get("question", "")
                        conversations.append(session, conversation_id, "assistant", text)
                    elif event.type == "confirmation":
                        waiting = f"Waiting for approval: {event.data['summary']}"
                        conversations.append(session, conversation_id, "assistant", waiting)
                    yield event
            except LLMError as exc:
                yield AgentEvent("error", {
                    "code": "llm_error", "message": str(exc), "hint": exc.hint,
                    "detail": exc.detail,
                })

    return sse_response(events(), debug=services.settings.debug)


@router.post("/{conversation_id}/confirm")
def confirm(conversation_id: str, body: ActionRef, request: Request) -> Any:
    """Execute the stored action and stream action → observation → answer.

    The execution commits itself in short transactions (see `execute_pending`)
    and its idempotency key is the one stored on the action, so a client
    cannot supply a different key per request. Success frames are streamed
    only once the result is durable; the narrator then runs with no
    transaction open, and its sentence is stored in one more short one.
    """
    services = request.app.state.services
    with session_scope(services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.actor != ACTOR or row.conversation_id != conversation_id:
            raise UnknownAction()
        if row.status == "executing":
            raise InProgress()
        if row.status != "pending":
            raise AlreadyDecided(row.status)

    def events() -> Iterator[AgentEvent]:
        """Claim and execute, then narrate, then record the sentence."""
        with session_scope(services.engine) as session:
            try:
                execution = execute_pending(
                    session=session, action_id=body.action_id, registry=OWNER_REGISTRY,
                    ctx=_ctx(request, session), expected_actor=ACTOR,
                )
            except ConfirmationError as exc:
                yield AgentEvent(
                    "error", {"code": exc.code, "message": str(exc), "hint": ""}
                )
                return
            except StripeGatewayError as exc:
                yield AgentEvent("error", {
                    "code": "stripe_error", "message": str(exc), "hint": exc.hint,
                    "detail": exc.detail,
                })
                return
        # From here the execution is durable: a dropped stream or a slow
        # narrator changes nothing about what Stripe did or what is recorded.
        yield AgentEvent("action", {"name": execution.action, "args": execution.parameters})
        yield AgentEvent(
            "observation", {"name": execution.action, "result": execution.result}
        )
        try:
            text = narrate_result(
                services.llm, action=execution.action, summary=execution.summary,
                result=execution.result, currency=services.gateway.default_currency(),
            )
        except LLMError:
            text = _done(execution.summary)
        with session_scope(services.engine) as session:
            conversations.append(session, conversation_id, "assistant", text)
        yield AgentEvent(
            "answer",
            {"text": text, "result": {"action": execution.action, "data": execution.result}},
        )

    return sse_response(events(), debug=services.settings.debug)


@router.post("/{conversation_id}/cancel")
def cancel(conversation_id: str, body: ActionRef, request: Request) -> dict[str, str]:
    """Dismiss a pending action so it can never be approved."""
    with session_scope(request.app.state.services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.actor != ACTOR or row.conversation_id != conversation_id:
            raise UnknownAction()
        if not pending_actions.cancel(session, body.action_id, actor=ACTOR):
            raise AlreadyDecided(row.status)
    return {"status": "cancelled"}


@router.get("/{conversation_id}")
def history(conversation_id: str, request: Request) -> dict[str, Any]:
    """Transcript plus the proposal a reloaded UI should still show."""
    with session_scope(request.app.state.services.engine) as session:
        messages = conversations.history(session, conversation_id, limit=200)
        pending = pending_actions.latest_pending(session, conversation_id)
        return {
            "conversation_id": conversation_id,
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in messages
            ],
            "pending": None if pending is None else {
                "action_id": pending.id, "action": pending.action, "summary": pending.summary,
                "parameters": json.loads(pending.parameters_json),
            },
        }
