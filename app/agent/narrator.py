"""Turn typed results into a sentence or two, where no planner is in the loop."""

import json
from typing import Any

from app.agent.events import to_jsonable
from app.agent.prompts import result_system, summary_system
from app.domain.summary import DailyFacts
from app.llm.base import ChatMessage, LLMBackend


def narrate_summary(llm: LLMBackend, facts: DailyFacts) -> str:
    """The daily summary paragraph, from facts computed in Python."""
    return llm.complete(
        system=summary_system(),
        messages=[ChatMessage(role="user", content=json.dumps(to_jsonable(facts)))],
        max_tokens=400,
    ).strip()


def narrate_result(llm: LLMBackend, *, action: str, summary: str, result: Any) -> str:
    """Confirm an executed action, anchored to the summary the user approved."""
    payload = {"action": action, "approved_summary": summary, "result": to_jsonable(result)}
    return llm.complete(
        system=result_system(),
        messages=[ChatMessage(role="user", content=json.dumps(payload))],
        max_tokens=300,
    ).strip()
