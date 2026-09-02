"""The propose→execute loop.

The model proposes one JSON action per step; Python executes it and feeds
the typed observation back. `answer` and `clarify` end the turn. A mutation
ends the turn with a `confirmation` event and nothing executed. The loop is
capped so a confused model cannot spin.
"""

import json
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.agent.events import AgentEvent, to_jsonable
from app.agent.executor import ActionError, parse_call, resolve, validate_params
from app.agent.schema import DISPLAY_KEY, TERMINAL_ACTIONS, ActionSpec, Registry
from app.domain.policy import MAX_AGENT_ITERATIONS
from app.llm.base import ChatMessage, LLMBackend, extract_json_object
from app.stripe_.gateway import StripeGatewayError

log = logging.getLogger(__name__)

GIVE_UP_TEXT = "I couldn't finish that in a few steps. Could you rephrase or narrow it down?"
RETRY_TEXT = "I made a mistake on that step and am trying again."


class ProposeHook(Protocol):
    """Stores a fully resolved proposal and returns its action_id."""

    def __call__(self, spec: ActionSpec, params: BaseModel, summary: str) -> str:
        """Persist the proposal and return the id shown to the user."""
        ...


class AuditHook(Protocol):
    """Records one executed action."""

    def __call__(
        self, action: str, parameters: dict[str, Any], result: Any, mutation: bool
    ) -> None:
        """Append one audit entry."""
        ...


@dataclass(frozen=True)
class TurnHooks:
    """Side effects the loop needs but must not own: storing proposals and auditing."""

    propose: ProposeHook
    audit: AuditHook


def _feedback(
    transcript: list[ChatMessage],
    raw: str,
    observation: dict[str, Any],
    label: str,
) -> None:
    """Append the model's step and our observation so the next call sees both."""
    transcript.append(ChatMessage(role="assistant", content=raw))
    observation_json = json.dumps(observation)
    transcript.append(
        ChatMessage(role="user", content=f"Observation for {label}: {observation_json}")
    )


def for_model(observation: Any) -> Any:
    """The observation as the planner reads it: the result minus interface-only data.

    Per-day totals in the transcript once led the planner to run a single
    two-week query and sum the halves itself — the arithmetic this loop exists
    to keep out of the model. See `DISPLAY_KEY`.
    """
    if isinstance(observation, dict) and DISPLAY_KEY in observation:
        return {key: value for key, value in observation.items() if key != DISPLAY_KEY}
    return observation


def _retry_event(exc: Exception) -> AgentEvent:
    """The trail line for a planner mistake the loop is about to correct.

    The owner reads one sentence. The raw parse or validation text is kept as
    `detail`, which the API boundary logs and sends only when DEBUG=1; the
    model itself still gets the exact text through `_feedback`.
    """
    return AgentEvent("error", {
        "code": "planner_retry", "message": RETRY_TEXT, "hint": "", "detail": str(exc),
    })


def run_turn(
    *,
    llm: LLMBackend,
    registry: Registry,
    ctx: Any,
    system: str,
    history: Sequence[ChatMessage],
    prompt: str,
    hooks: TurnHooks,
) -> Iterator[AgentEvent]:
    """Run one user turn, yielding events as they happen.

    Args:
        llm: The planner model.
        registry: The channel's actions — owner or customer, never both.
        ctx: Passed verbatim to handlers; carries the (scoped) gateway and session.
        system: The planner system prompt for this channel.
        history: Prior turns, oldest first.
        prompt: The user's new message.
        hooks: How to store a proposal and how to audit an execution.
    """
    transcript: list[ChatMessage] = [*history, ChatMessage(role="user", content=prompt)]
    for _ in range(MAX_AGENT_ITERATIONS):
        raw = llm.complete(system=system, messages=transcript)
        try:
            call = parse_call(extract_json_object(raw))
        except (ValueError, ActionError) as exc:
            yield _retry_event(exc)
            _feedback(transcript, raw, {"error": str(exc)}, "invalid step")
            continue
        if call.reasoning:
            yield AgentEvent("planning", {"reasoning": call.reasoning})
        if call.action in TERMINAL_ACTIONS:
            try:
                terminal = validate_params(TERMINAL_ACTIONS[call.action], call.parameters)
            except ValidationError as exc:
                yield _retry_event(exc)
                _feedback(transcript, raw, {"error": f"Invalid {call.action}: {exc}"}, call.action)
                continue
            yield AgentEvent(call.action, terminal.model_dump())  # type: ignore[arg-type]
            return
        try:
            spec, params = resolve(registry, call)
        except ActionError as exc:
            yield _retry_event(exc)
            _feedback(transcript, raw, {"error": str(exc)}, call.action)
            continue
        args = params.model_dump(mode="json")
        yield AgentEvent("action", {"name": spec.name, "args": args})
        try:
            if spec.mutation:
                assert spec.describe is not None  # enforced by ActionSpec.__post_init__
                proposal = spec.describe(ctx, params)
                if proposal.summary is not None:
                    action_id = hooks.propose(spec, params, proposal.summary)
                    yield AgentEvent("confirmation", {
                        "action_id": action_id, "action": spec.name,
                        "summary": proposal.summary, "parameters": args,
                        "details": to_jsonable(proposal.details),
                    })
                    return
                result: Any = proposal.resolved
            else:
                result = spec.handler(ctx, params)
        except ActionError as exc:
            result = {"error": str(exc)}
        except StripeGatewayError as exc:
            # The observation feeds the model and the trail; developer detail
            # belongs in neither, and this is its only exit, so log it here.
            if exc.detail:
                log.warning("%s failed: %s (%s)", spec.name, exc, exc.detail)
            result = {"error": str(exc), "hint": exc.hint}
        else:
            hooks.audit(spec.name, args, to_jsonable(result), False)
        observation = to_jsonable(result)
        yield AgentEvent("observation", {"name": spec.name, "result": observation})
        _feedback(transcript, raw, for_model(observation), spec.name)
    yield AgentEvent("answer", {"text": GIVE_UP_TEXT})
