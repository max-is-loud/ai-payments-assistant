"""Conversational routes: send a turn, confirm or cancel a proposal, read history."""

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.actions.context import OwnerContext
from app.actions.owner_registry import build_owner_registry
from app.agent.confirm import ConfirmationError, UnknownAction, execute_pending
from app.agent.events import AgentEvent
from app.agent.loop import TurnHooks, run_turn
from app.agent.narrator import narrate_result
from app.agent.prompts import OWNER_NOTES, planner_system
from app.api.auth import require_owner
from app.api.sse import sse_response
from app.db import audit, conversations, pending_actions
from app.db.engine import session_scope
from app.domain.periods import local_timezone
from app.llm.base import ChatMessage, LLMError
from app.stripe_.gateway import StripeGatewayError

router = APIRouter(prefix="/api/conversations", dependencies=[Depends(require_owner)])
OWNER_REGISTRY = build_owner_registry()
CHANNEL, ACTOR = "web", "owner"


class MessageIn(BaseModel):
    """A user turn."""

    text: str = Field(..., min_length=1, max_length=2000)


class ActionRef(BaseModel):
    """Reference to a pending action."""

    action_id: str


def _ctx(request: Request, session: Session, idempotency_key: str | None = None) -> OwnerContext:
    """Owner context over the process services."""
    services = request.app.state.services
    return OwnerContext(
        gateway=services.gateway, session=session, now=datetime.now(local_timezone()),
        notify=services.notify, idempotency_key=idempotency_key,
    )


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
            system = planner_system(
                registry=OWNER_REGISTRY, today=ctx.now.date(), channel_notes=OWNER_NOTES
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
                yield AgentEvent(
                    "error", {"code": "llm_error", "message": str(exc), "hint": exc.hint}
                )

    return sse_response(events())


@router.post("/{conversation_id}/confirm")
def confirm(
    conversation_id: str, body: ActionRef, request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Execute the stored action and stream action → observation → answer."""
    services = request.app.state.services
    with session_scope(services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.actor != ACTOR or row.conversation_id != conversation_id:
            raise UnknownAction()
        if row.status != "pending":
            raise ConfirmationError("already_decided", f"That action was already {row.status}.")

    def events() -> Iterator[AgentEvent]:
        """Claim, execute, narrate."""
        with session_scope(services.engine) as session:
            try:
                execution = execute_pending(
                    session=session, action_id=body.action_id, registry=OWNER_REGISTRY,
                    ctx=_ctx(request, session, idempotency_key), expected_actor=ACTOR,
                    idempotency_key=idempotency_key,
                )
            except ConfirmationError as exc:
                yield AgentEvent(
                    "error", {"code": exc.code, "message": str(exc), "hint": ""}
                )
                return
            except StripeGatewayError as exc:
                yield AgentEvent(
                    "error", {"code": "stripe_error", "message": str(exc), "hint": exc.hint}
                )
                return
            yield AgentEvent("action", {"name": execution.action, "args": execution.parameters})
            yield AgentEvent(
                "observation", {"name": execution.action, "result": execution.result}
            )
            try:
                text = narrate_result(
                    services.llm, action=execution.action, summary=execution.summary,
                    result=execution.result,
                )
            except LLMError:
                text = f"Done: {execution.summary}."
            conversations.append(session, conversation_id, "assistant", text)
            yield AgentEvent(
                "answer",
                {"text": text, "result": {"action": execution.action, "data": execution.result}},
            )

    return sse_response(events())


@router.post("/{conversation_id}/cancel")
def cancel(conversation_id: str, body: ActionRef, request: Request) -> dict[str, str]:
    """Dismiss a pending action so it can never be approved."""
    with session_scope(request.app.state.services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.conversation_id != conversation_id:
            raise UnknownAction()
        if not pending_actions.cancel(session, body.action_id):
            raise ConfirmationError("already_decided", f"That action was already {row.status}.")
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
