"""JSON extraction tolerates the ways models wrap JSON, and rejects the rest."""

import pytest

from app.llm.base import extract_json_object


def test_extracts_from_code_fence_and_surrounding_prose() -> None:
    """Models sometimes fence or preface JSON despite instructions; both must parse."""
    fenced = 'Sure:\n```json\n{"action": "answer", "parameters": {"text": "hi"}}\n```'
    assert extract_json_object(fenced)["action"] == "answer"
    plain = '{"action": "clarify", "parameters": {"question": "Which Maya?"}} trailing'
    assert extract_json_object(plain)["parameters"]["question"] == "Which Maya?"


def test_first_complete_object_wins_over_trailing_braces() -> None:
    """A second object, or a note with a brace after the real one, must not poison the parse."""
    doubled = '{"action": "answer", "parameters": {"text": "one"}}\n{"action": "answer"}'
    assert extract_json_object(doubled)["parameters"]["text"] == "one"
    noted = 'Plan {draft}: {"action": "clarify", "parameters": {"question": "Which?"}} — {done}'
    assert extract_json_object(noted)["action"] == "clarify"


def test_non_object_or_garbage_raises() -> None:
    """A list, or no JSON at all, is a planner failure the loop reports back to the model."""
    with pytest.raises(ValueError):
        extract_json_object("[1, 2]")
    with pytest.raises(ValueError):
        extract_json_object("I refuse to answer in JSON")
