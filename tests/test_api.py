"""HTTP contract: auth with a hint, typed SSE events, stored-action confirmation, resources."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.app import Services, create_app
from app.db import escalations, pending_actions
from app.db.engine import session_scope
from app.settings import Settings
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway

AUTH = {"Authorization": "Bearer test-token"}
NOW = datetime.now(UTC)


def _step(action: str, **parameters: Any) -> str:
    """A planner step as the LLM would emit it."""
    return json.dumps({"reasoning": "r", "action": action, "parameters": parameters})


def _events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event, data) pairs."""
    out: list[tuple[str, dict[str, Any]]] = []
    event = ""
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            out.append((event, json.loads(line.split(":", 1)[1].strip())))
    return out


@pytest.fixture
def world(engine: Engine) -> Iterator[tuple[TestClient, FakeStripeGateway, ScriptedLLM, list[Any]]]:
    """A test app over fakes: Maya paid $90 today; the LLM script is filled per test."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_payment("pi_1", "cus_maya", 9000, occurred_at=NOW - timedelta(minutes=5))
    fake.add_invoice("in_1", "cus_acme", 120000)
    llm = ScriptedLLM([])
    sent: list[Any] = []
    services = Services(
        settings=Settings(
            _env_file=None, owner_api_token="test-token", stripe_secret_key="sk_test_x"
        ),
        gateway=fake, llm=llm, engine=engine,
        notify=lambda tid, text, url: (sent.append((tid, text, url)), True)[1],
    )
    with TestClient(create_app(services)) as client:
        yield client, fake, llm, sent


def test_missing_token_returns_envelope_with_hint(world: Any) -> None:
    """401 tells the reviewer exactly which header and variable to use."""
    client, *_ = world
    response = client.get("/api/summary/today")
    assert response.status_code == 401
    body = response.json()["error"]
    assert body["code"] == "unauthorized" and "OWNER_API_TOKEN" in body["hint"]


def test_message_turn_streams_typed_events_and_persists_history(world: Any) -> None:
    """Planning → action → observation → answer, then the transcript is retrievable."""
    client, _fake, llm, _ = world
    llm._responses.extend(
        [_step("find_customer", query="maya"), _step("answer", text="Found Maya Chen.")]
    )
    with client.stream(
        "POST", "/api/conversations/c1/messages", json={"text": "who is maya"}, headers=AUTH
    ) as r:
        assert r.status_code == 200
        events = _events(r)
    assert [e for e, _ in events] == ["planning", "action", "observation", "planning", "answer"]
    assert events[1][1] == {"name": "find_customer", "args": {"query": "maya"}}
    history = client.get("/api/conversations/c1", headers=AUTH).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["pending"] is None


def test_confirmation_executes_the_stored_action_once_with_the_header_key(world: Any) -> None:
    """Approve runs exactly the proposal; the header becomes Stripe's key; repeats 409."""
    client, fake, llm, _ = world
    llm._responses.extend(
        [_step("refund_payment", payment_id="pi_1", amount_cents=4500), "Refunded $45.00."]
    )
    with client.stream(
        "POST", "/api/conversations/c1/messages", json={"text": "refund maya 45"}, headers=AUTH
    ) as r:
        events = _events(r)
    assert events[-1][0] == "confirmation"
    action_id = events[-1][1]["action_id"]
    assert events[-1][1]["summary"].startswith("Refund $45.00 to Maya Chen")
    pending = client.get("/api/conversations/c1", headers=AUTH).json()["pending"]
    assert pending["action_id"] == action_id
    with client.stream("POST", "/api/conversations/c1/confirm", json={"action_id": action_id},
                       headers={**AUTH, "Idempotency-Key": "idem-1"}) as r:
        confirmed = _events(r)
    assert [e for e, _ in confirmed] == ["action", "observation", "answer"]
    assert confirmed[-1][1]["text"] == "Refunded $45.00."
    assert [c for c in fake.calls if c[0] == "refund"] == [
        ("refund", {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": "idem-1"})
    ]
    again = client.post(
        "/api/conversations/c1/confirm", json={"action_id": action_id}, headers=AUTH
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_decided"
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1
    audit = client.get("/api/audit", headers=AUTH).json()
    assert audit[0]["action"] == "refund_payment" and audit[0]["mutation"] is True


def test_cancel_dismisses_a_pending_action(world: Any) -> None:
    """Cancel is a resource change: the action can no longer be confirmed."""
    client, _fake, llm, _ = world
    llm._responses.append(_step("create_payment_link", amount_cents=5000, description="Deposit"))
    with client.stream(
        "POST", "/api/conversations/c2/messages", json={"text": "link for 50"}, headers=AUTH
    ) as r:
        action_id = _events(r)[-1][1]["action_id"]
    cancelled = client.post(
        "/api/conversations/c2/cancel", json={"action_id": action_id}, headers=AUTH
    )
    assert cancelled.json() == {"status": "cancelled"}
    confirmed = client.post(
        "/api/conversations/c2/confirm", json={"action_id": action_id}, headers=AUTH
    )
    assert confirmed.status_code == 409


def test_confirm_stream_error_frame_carries_a_hint(world: Any, engine: Engine) -> None:
    """SSE error frames match the HTTP envelope's three fields, even mid-stream.

    The route's pre-stream check only inspects status/actor/conversation, so it
    cannot catch stored parameters that no longer validate; that failure surfaces
    from `execute_pending` inside the `events()` generator instead, which is the
    branch this test exercises (unlike the cancelled-action case above, which the
    pre-stream check rejects with a plain 409 before any SSE frame is emitted).
    """
    client, *_ = world
    with session_scope(engine) as session:
        row = pending_actions.create(
            session, conversation_id="c3", channel="web", actor="owner",
            action="refund_payment", parameters={"payment_id": 123},
            summary="Invalid refund", prompt="test",
        )
        action_id = row.id
    with client.stream(
        "POST", "/api/conversations/c3/confirm", json={"action_id": action_id}, headers=AUTH
    ) as r:
        events = _events(r)
    assert [e for e, _ in events] == ["error"]
    assert events[0][1]["code"] == "invalid_stored_action"
    assert set(events[0][1]) == {"code", "message", "hint"}


def test_summary_facts_without_narration(world: Any) -> None:
    """narrate=false returns facts only, for the live rail, without an LLM call."""
    client, _fake, llm, _ = world
    body = client.get("/api/summary/today?narrate=false", headers=AUTH).json()
    assert body["text"] is None and body["facts"]["today"]["succeeded_total_cents"] == 9000
    assert llm.calls == []
    llm._responses.append("You took $90.00 today.")
    narrated = client.get("/api/summary/today", headers=AUTH).json()
    assert narrated["text"] == "You took $90.00 today."


def test_escalation_approval_and_binding_revocation(world: Any, engine: Engine) -> None:
    """The bonus loop's owner side and the owner-side revoke, as plain resources."""
    client, _fake, _llm, sent = world
    with session_scope(engine) as session:
        esc_id = escalations.file(
            session, telegram_id=7, customer_id="cus_acme", customer_name="Acme Corp",
            invoice_id="in_1", amount_cents=120000, reason="ceiling", now=datetime.utcnow(),
        ).id
    assert [e["id"] for e in client.get("/api/escalations", headers=AUTH).json()] == [esc_id]
    approved = client.post(f"/api/escalations/{esc_id}/approve", headers=AUTH).json()
    assert approved["notified"] is True and sent[0][2] == "https://invoice.example/in_1"
    assert client.get("/api/escalations", headers=AUTH).json() == []
    assert client.post("/api/escalations/esc_nope/approve", headers=AUTH).status_code == 404
    revoked = client.delete("/api/customers/cus_acme/telegram-binding", headers=AUTH)
    assert revoked.json() == {"revoked": 0}
