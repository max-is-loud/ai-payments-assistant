"""The narrator receives facts as JSON and returns the model's text, trimmed."""

import json
from datetime import UTC, datetime

from app.agent.narrator import narrate_result, narrate_summary
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
