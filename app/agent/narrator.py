"""Turn typed results into a sentence or two, where no planner is in the loop."""

import json
from datetime import date
from typing import Any

from app.agent.events import to_jsonable
from app.agent.prompts import result_system, summary_system
from app.domain.currency import Currency
from app.domain.money import formatted_amounts
from app.domain.summary import DailyFacts
from app.llm.base import ChatMessage, LLMBackend

# Narrators copy figures, they never convert them: every amount reaches the
# model already formatted in the account's currency (see `formatted_amounts`).


def narrate_summary(llm: LLMBackend, facts: DailyFacts, currency: Currency) -> str:
    """The daily summary paragraph, from facts computed in Python.

    The facts carry ISO dates only, and a model asked for "the day's mood" will
    otherwise guess the weekday; it is spelled out as `today_is` so the aside
    can say "Wednesday" and mean it.
    """
    today = date.fromisoformat(facts.today.label)
    payload = {
        "today_is": f"{today:%A}, {today:%B} {today.day}, {today.year}",
        **formatted_amounts(to_jsonable(facts), currency),
    }
    return llm.complete(
        system=summary_system(),
        messages=[ChatMessage(role="user", content=json.dumps(payload))],
        max_tokens=400,
    ).strip()


def narrate_result(
    llm: LLMBackend, *, action: str, summary: str, result: Any, currency: Currency
) -> str:
    """Confirm an executed action, anchored to the summary the user approved."""
    payload = {
        "action": action, "approved_summary": summary,
        "result": formatted_amounts(to_jsonable(result), currency),
    }
    return llm.complete(
        system=result_system(),
        messages=[ChatMessage(role="user", content=json.dumps(payload))],
        max_tokens=300,
    ).strip()
