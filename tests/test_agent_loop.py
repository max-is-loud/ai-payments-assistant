"""The loop: observe and iterate, stop on answer/clarify, pause on mutations, cap at five."""

import json
import logging
from typing import Any

import pytest
from pydantic import BaseModel

from app.agent.loop import GIVE_UP_TEXT, RETRY_TEXT, TurnHooks, run_turn
from app.agent.schema import ActionSpec, Proposal, Registry
from app.domain.policy import MAX_AGENT_ITERATIONS
from app.stripe_.gateway import StripeGatewayError
from tests.fakes.llm_fake import ScriptedLLM


class EchoParams(BaseModel):
    """Echo parameters."""

    text: str


class RefundParams(BaseModel):
    """Refund parameters."""

    payment_id: str
    amount_cents: int | None = None


def _echo(_ctx: dict[str, Any], params: EchoParams) -> dict[str, str]:
    """Non-mutating action."""
    return {"echo": params.text}


def _describe_refund(_ctx: dict[str, Any], params: RefundParams) -> Proposal:
    """Resolve the refund into a human summary."""
    return Proposal(summary=f"Refund {params.payment_id}")


def _refund(ctx: dict[str, Any], params: RefundParams) -> dict[str, bool]:
    """Mutating action; records that it ran."""
    ctx["refunds"].append(params.payment_id)
    return {"ok": True}


REGISTRY = Registry([
    ActionSpec("echo", "Echo text", EchoParams, _echo),
    ActionSpec(
        "refund",
        "Refund a payment",
        RefundParams,
        _refund,
        mutation=True,
        describe=_describe_refund,
    ),
])


def _call(action: str, **parameters: Any) -> str:
    """Serialise a planner step."""
    return json.dumps({"reasoning": f"do {action}", "action": action, "parameters": parameters})


def _hooks(proposals: list[str], audits: list[str]) -> TurnHooks:
    """Hooks that record instead of persisting."""
    return TurnHooks(
        propose=lambda spec, params, summary: (proposals.append(summary), "act_1")[1],
        audit=lambda action, parameters, result, mutation: audits.append(action),
    )


def _run(
    llm: ScriptedLLM,
    ctx: dict[str, Any] | None = None,
    hooks: TurnHooks | None = None,
) -> list[Any]:
    """Drive a turn to completion and collect events."""
    return list(run_turn(
        llm=llm,
        registry=REGISTRY,
        ctx=ctx or {"refunds": []},
        system="sys",
        history=[],
        prompt="hello",
        hooks=hooks or _hooks([], []),
    ))


def test_observation_then_answer() -> None:
    """A read action produces an observation the planner sees before answering."""
    llm = ScriptedLLM([_call("echo", text="hi"), _call("answer", text="Done")])
    audits: list[str] = []
    events = _run(llm, hooks=_hooks([], audits))
    assert [e.type for e in events] == ["planning", "action", "observation", "planning", "answer"]
    assert events[2].data["result"] == {"echo": "hi"}
    assert events[-1].data["text"] == "Done"
    assert audits == ["echo"]
    assert "Observation for echo" in llm.calls[1][1][-1].content


def test_mutation_pauses_for_confirmation_without_executing() -> None:
    """Proposing a refund stores it and stops; nothing is refunded and the LLM is not re-asked."""
    llm = ScriptedLLM([_call("refund", payment_id="pi_1")])
    ctx: dict[str, Any] = {"refunds": []}
    proposals: list[str] = []
    events = _run(llm, ctx, _hooks(proposals, []))
    assert events[-1].type == "confirmation"
    assert events[-1].data == {
        "action_id": "act_1", "action": "refund", "summary": "Refund pi_1",
        "parameters": {"payment_id": "pi_1", "amount_cents": None},
    }
    assert ctx["refunds"] == []
    assert proposals == ["Refund pi_1"]
    assert len(llm.calls) == 1


def test_loop_is_capped() -> None:
    """A model that never answers is cut off after MAX_AGENT_ITERATIONS steps."""
    llm = ScriptedLLM([_call("echo", text="again")] * (MAX_AGENT_ITERATIONS + 3))
    events = _run(llm)
    assert len(llm.calls) == MAX_AGENT_ITERATIONS
    assert events[-1].type == "answer"
    assert events[-1].data["text"] == GIVE_UP_TEXT


def test_bad_json_and_unknown_actions_are_fed_back_not_fatal() -> None:
    """The planner gets one chance per mistake to correct itself."""
    llm = ScriptedLLM(["not json at all", _call("nope"), _call("answer", text="ok")])
    events = _run(llm)
    assert [e.type for e in events] == ["error", "planning", "error", "planning", "answer"]
    assert "Unknown action" in llm.calls[2][1][-1].content


def test_planner_mistakes_read_as_a_retry_with_the_raw_text_kept_as_detail() -> None:
    """The owner reads one plain sentence; the parse error rides along as developer detail.

    The model still receives the exact error as feedback (asserted above); this
    only changes what the trail shows for the same step.
    """
    llm = ScriptedLLM(["not json at all", _call("answer", text="ok")])
    error = _run(llm)[0]
    assert error.type == "error"
    assert error.data["code"] == "planner_retry" and error.data["message"] == RETRY_TEXT
    assert "JSON" not in error.data["message"] and "JSON" in error.data["detail"]


def test_stripe_detail_from_a_failed_action_is_logged_and_kept_from_the_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The observation stays {error, hint} for the model and the trail; SDK text goes to the log."""

    def failing(_ctx: Any, _params: EchoParams) -> dict[str, str]:
        """A handler whose Stripe call failed with developer detail attached."""
        raise StripeGatewayError(
            "Stripe couldn't complete that.", hint="Try again.", detail="Connection reset"
        )

    registry = Registry([ActionSpec("echo", "Echo text", EchoParams, failing)])
    llm = ScriptedLLM([_call("echo", text="hi"), _call("answer", text="ok")])
    with caplog.at_level(logging.WARNING, logger="app.agent.loop"):
        events = list(run_turn(
            llm=llm, registry=registry, ctx={}, system="sys", history=[], prompt="go",
            hooks=_hooks([], []),
        ))
    observation = events[2].data["result"]
    assert observation == {"error": "Stripe couldn't complete that.", "hint": "Try again."}
    assert "Connection reset" in caplog.text
    assert "Connection reset" not in llm.calls[1][1][-1].content
