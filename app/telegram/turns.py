"""Synchronous glue between Telegram updates and the agent.

Handlers call these through `asyncio.to_thread`. Everything here runs the
customer registry over a gateway bound to the customer from the binding row.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.actions.context import CustomerContext
from app.actions.customer import PayInvoiceParams, build_customer_registry
from app.agent.confirm import ConfirmationError, execute_pending
from app.agent.events import AgentEvent
from app.agent.executor import ActionError
from app.agent.loop import TurnHooks, run_turn
from app.agent.prompts import telegram_planner_system
from app.db import audit, bindings, conversations, pending_actions
from app.db.clock import utcnow
from app.db.engine import session_scope
from app.db.models import TelegramBinding
from app.domain.periods import local_timezone
from app.llm.base import ChatMessage, LLMBackend, LLMError
from app.settings import Settings
from app.stripe_.customer_client import CustomerScopedGateway
from app.stripe_.gateway import StripeGateway, StripeGatewayError
from app.telegram.render import ERROR_TEXT, Reply, receipt_reply

CUSTOMER_REGISTRY = build_customer_registry()
CHANNEL = "telegram"

log = logging.getLogger(__name__)


@dataclass
class BotDeps:
    """Process-wide dependencies for the bot."""

    settings: Settings
    gateway: StripeGateway
    llm: LLMBackend
    engine: Engine


def _actor(telegram_id: int) -> str:
    """Actor string stored on pending actions and audit rows."""
    return f"telegram:{telegram_id}"


def _ctx(deps: BotDeps, session: Session, binding: TelegramBinding) -> CustomerContext:
    """A context whose gateway is bound to the customer on the binding row."""
    return CustomerContext(
        gateway=CustomerScopedGateway(deps.gateway, binding.stripe_customer_id),
        session=session,
        telegram_id=binding.telegram_id,
        customer_name=binding.customer_name,
        now=datetime.now(local_timezone()),
    )


def _hooks(session: Session, binding: TelegramBinding, prompt: str) -> TurnHooks:
    """Persist proposals and audit rows, committing immediately (shared SQLite file)."""
    def propose(spec: Any, params: Any, summary: str) -> str:
        """Store the proposal under this Telegram actor."""
        actor = _actor(binding.telegram_id)
        row = pending_actions.create(
            session, conversation_id=actor, channel=CHANNEL, actor=actor,
            action=spec.name, parameters=params.model_dump(mode="json"), summary=summary,
            prompt=prompt,
        )
        session.commit()
        return row.id

    def record(action: str, parameters: dict[str, Any], result: Any, mutation: bool) -> None:
        """Audit."""
        audit.record(
            session, channel=CHANNEL, actor=_actor(binding.telegram_id), prompt=prompt,
            action=action, parameters=parameters, result=result, mutation=mutation,
        )
        session.commit()

    return TurnHooks(propose=propose, audit=record)


def bind_token(deps: BotDeps, telegram_id: int, token: str) -> str | None:
    """Bind a Telegram account via a seed-minted token; returns the customer name or None."""
    customer = deps.gateway.find_customer_by_bind_token(token.strip())
    if customer is None:
        return None
    with session_scope(deps.engine) as session:
        bindings.bind(
            session, telegram_id=telegram_id, customer_id=customer.id,
            customer_name=customer.name, now=utcnow(),
        )
    return customer.name


def resolve_customer(deps: BotDeps, telegram_id: int) -> TelegramBinding | None:
    """The active binding, renewed, or None. Detached from its session for use in handlers."""
    with session_scope(deps.engine) as session:
        row = bindings.resolve(session, telegram_id, utcnow())
        if row is not None:
            session.expunge(row)
        return row


def revoke(deps: BotDeps, telegram_id: int) -> bool:
    """`/logout`."""
    with session_scope(deps.engine) as session:
        return bindings.revoke(session, telegram_id, utcnow())


def customer_turn(deps: BotDeps, binding: TelegramBinding, text: str) -> list[AgentEvent]:
    """Run one turn of the customer agent and return every event."""
    conversation_id = _actor(binding.telegram_id)
    with session_scope(deps.engine) as session:
        conversations.ensure(session, conversation_id, CHANNEL)
        history = [ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
                   for m in conversations.history(session, conversation_id)]
        conversations.append(session, conversation_id, "user", text)
        session.commit()
        ctx = _ctx(deps, session, binding)
        system = telegram_planner_system(registry=CUSTOMER_REGISTRY, today=ctx.now.date())
        try:
            events = list(run_turn(
                llm=deps.llm, registry=CUSTOMER_REGISTRY, ctx=ctx, system=system,
                history=history, prompt=text, hooks=_hooks(session, binding, text),
            ))
        except LLMError as exc:
            return [AgentEvent("error", {"message": str(exc)})]
        last = events[-1]
        if last.type in ("answer", "clarify"):
            reply_text = last.data.get("text") or last.data.get("question", "")
            conversations.append(session, conversation_id, "assistant", reply_text)
        return events


def propose_payment(deps: BotDeps, binding: TelegramBinding, invoice_id: str) -> list[AgentEvent]:
    """The Pay button: propose `pay_invoice` deterministically, no planner involved."""
    spec = CUSTOMER_REGISTRY.get("pay_invoice")
    assert spec is not None and spec.describe is not None
    params = PayInvoiceParams(invoice_id=invoice_id)
    with session_scope(deps.engine) as session:
        ctx = _ctx(deps, session, binding)
        try:
            proposal = spec.describe(ctx, params)
        except (ActionError, StripeGatewayError) as exc:
            return [AgentEvent("answer", {"text": str(exc)})]
        if proposal.summary is None:
            return [AgentEvent("answer", {"text": proposal.resolved["message"]})]
        hooks = _hooks(session, binding, f"(tapped Pay {invoice_id})")
        action_id = hooks.propose(spec, params, proposal.summary)
        return [AgentEvent("confirmation", {
            "action_id": action_id, "action": spec.name,
            "summary": proposal.summary, "parameters": params.model_dump(),
        })]


def confirm_action(deps: BotDeps, binding: TelegramBinding, action_id: str) -> Reply:
    """The Confirm button: execute the stored action for this Telegram actor only."""
    with session_scope(deps.engine) as session:
        try:
            execution = execute_pending(
                session=session, action_id=action_id, registry=CUSTOMER_REGISTRY,
                ctx=_ctx(deps, session, binding), expected_actor=_actor(binding.telegram_id),
            )
        except ConfirmationError as exc:
            return Reply(str(exc))
        except (ActionError, StripeGatewayError) as exc:
            return Reply(f"I couldn't complete that: {exc}")
        except Exception:
            log.exception("confirm_action failed for %s", action_id)
            return Reply(ERROR_TEXT)
    if execution.action == "pay_invoice":
        return receipt_reply(execution.result)
    return Reply(f"Done: {execution.summary}.")


def cancel_action(deps: BotDeps, action_id: str) -> None:
    """The Cancel button."""
    with session_scope(deps.engine) as session:
        pending_actions.cancel(session, action_id)
