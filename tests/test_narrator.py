"""The narrator receives facts as JSON and returns the model's text, trimmed."""

import json
from datetime import UTC, datetime

from app.agent.narrator import narrate_result, narrate_summary
from app.domain.models import Payment
from app.domain.summary import build_daily_facts
from tests.fakes.llm_fake import ScriptedLLM


def test_summary_narration_sends_facts_json() -> None:
    """Every number the model may quote is in the JSON it receives."""
    facts = build_daily_facts([], [], datetime(2026, 9, 1, tzinfo=UTC))
    llm = ScriptedLLM(["  Quiet day so far.  "])
    assert narrate_summary(llm, facts) == "Quiet day so far."
    payload = json.loads(llm.calls[0][1][0].content)
    assert payload["today"]["succeeded_count"] == 0


def test_result_narration_includes_the_approved_summary() -> None:
    """The narration is anchored to what the user approved, not a re-interpretation."""
    llm = ScriptedLLM(["Refunded."])
    assert (
        narrate_result(
            llm,
            action="refund_payment",
            summary="Refund $45.00 to Maya Chen",
            result={"ok": True},
        )
        == "Refunded."
    )
    assert "Refund $45.00 to Maya Chen" in llm.calls[0][1][0].content


def test_narrators_receive_dollars_never_cents() -> None:
    """A model shown 257800 has written $257,800.00 beside a hero that says $2,578.00.

    Both narrators get every amount pre-formatted, so the prose can only copy.
    """
    now = datetime(2026, 9, 1, 15, tzinfo=UTC)
    payment = Payment(
        id="pi", charge_id="ch", customer_id="cus", customer_name="Maya Chen", amount_cents=257800,
        amount_refunded_cents=0, status="succeeded", failure_reason=None, description=None,
        occurred_at=now,
    )
    llm = ScriptedLLM(["ok", "ok"])
    narrate_summary(llm, build_daily_facts([payment], [], now))
    summary_payload = llm.calls[0][1][0].content
    assert '"$2,578.00"' in summary_payload
    assert "257800" not in summary_payload and "_cents" not in summary_payload
    narrate_result(
        llm, action="refund_payment", summary="s",
        result={"amount_cents": 4500, "refund_id": "re_1"},
    )
    result_payload = llm.calls[1][1][0].content
    assert '"$45.00"' in result_payload and "4500" not in result_payload


def test_summary_narration_names_the_weekday_so_the_model_never_guesses_it() -> None:
    """The facts carry ISO dates only; "A quiet Tuesday" on a Wednesday came from guessing."""
    llm = ScriptedLLM(["ok"])
    narrate_summary(llm, build_daily_facts([], [], datetime(2026, 9, 2, 15, tzinfo=UTC)))
    payload = json.loads(llm.calls[0][1][0].content)
    assert payload["today_is"] == "Wednesday, September 2, 2026"
    assert payload["today"]["succeeded_count"] == 0
