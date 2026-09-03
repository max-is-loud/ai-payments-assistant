"""Bot replies: amounts never appear in free text; invoices become buttons."""

from app.agent.events import AgentEvent
from app.telegram.render import receipt_reply, reply_for


def test_answer_with_invoice_buttons() -> None:
    """An answer after my_invoices carries View/Pay buttons per open invoice."""
    invoice_row = {
        "invoice_id": "in_1", "number": "F-0001", "status": "open", "due_date": "2026-09-11",
        "description": "Q3 retainer", "view_url": "https://invoice.example/in_1",
    }
    events = [
        AgentEvent("action", {"name": "my_invoices", "args": {}}),
        AgentEvent(
            "observation",
            {"name": "my_invoices", "result": {"count": 1, "invoices": [invoice_row]}},
        ),
        AgentEvent("answer", {"text": "You have 1 unpaid invoice, due Sep 11."}),
    ]
    reply = reply_for(events)
    assert reply.text == "You have 1 unpaid invoice, due Sep 11."
    labels = [b.text for row in reply.buttons for b in row]
    assert labels == ["View F-0001", "Pay F-0001"]
    assert reply.buttons[0][0].url == "https://invoice.example/in_1"
    assert reply.buttons[0][1].callback_data == "pay:in_1"


def test_confirmation_and_receipt() -> None:
    """A proposal shows the summary with Confirm/Cancel; a receipt links the hosted invoice."""
    confirmation = {
        "action_id": "act_1", "action": "pay_invoice",
        "summary": "Pay invoice F-0001 for $1,200.00 with your card on file",
        "parameters": {},
    }
    reply = reply_for([AgentEvent("confirmation", confirmation)])
    assert reply.text.endswith("?")
    assert [b.callback_data for b in reply.buttons[0]] == ["confirm:act_1", "cancel:act_1"]
    receipt = receipt_reply({
        "paid": True, "number": "F-0001", "receipt_url": "https://invoice.example/in_1",
    })
    assert "$" not in receipt.text
    assert "<b>F-0001</b>" in receipt.text
    assert receipt.buttons[0][0].url == "https://invoice.example/in_1"


def test_a_threshold_invoice_gets_pay_only_while_a_small_one_gets_view_and_pay() -> None:
    """One reply, two invoices: the hosted page is a button only where the bot may take payment."""
    small = {
        "invoice_id": "in_small", "number": "F-0001", "status": "open", "due_date": "2026-09-11",
        "description": "Q3 retainer", "view_url": "https://invoice.example/in_small",
        "requires_owner_approval": False,
    }
    big = {
        "invoice_id": "in_big", "number": "F-0002", "status": "open", "due_date": "2026-09-22",
        "description": "Annual licence", "view_url": None, "requires_owner_approval": True,
    }
    events = [
        AgentEvent("observation", {
            "name": "my_balance", "result": {"unpaid_count": 2, "invoices": [small, big]},
        }),
        AgentEvent("answer", {"text": "You have 2 unpaid invoices; one needs the owner."}),
    ]
    reply = reply_for(events)
    assert [[b.text for b in row] for row in reply.buttons] == [
        ["View F-0001", "Pay F-0001"], ["F-0002 · needs the owner's approval"],
    ]
    assert [b.url for b in reply.buttons[1]] == [None]
    assert reply.buttons[1][0].callback_data == "pay:in_big"
    assert "https://" not in reply.text


def test_amounts_appear_on_the_buttons_and_in_a_server_written_total() -> None:
    """The figure the customer needs is written by Python: on each Pay button and one total line."""
    small = {
        "invoice_id": "in_small", "number": "F-0001", "status": "open", "due_date": "2026-09-11",
        "description": "Q3 retainer", "view_url": "https://invoice.example/in_small",
        "requires_owner_approval": False,
    }
    big = {
        "invoice_id": "in_big", "number": "F-0002", "status": "open", "due_date": "2026-09-22",
        "description": "Annual licence", "view_url": None, "requires_owner_approval": True,
    }
    events = [
        AgentEvent("observation", {"name": "my_balance", "result": {
            "unpaid_count": 2, "invoices": [small, big],
            "display": {
                "invoice_amounts": {"in_small": "CA$1,200.00", "in_big": "CA$2,400.00"},
                "owed_total": "CA$3,600.00",
            },
        }}),
        AgentEvent("answer", {"text": "You have 2 unpaid invoices."}),
    ]
    reply = reply_for(events)
    assert [[b.text for b in row] for row in reply.buttons] == [
        ["View F-0001", "Pay F-0001 · CA$1,200.00"],
        ["F-0002 · CA$2,400.00 · needs the owner's approval"],
    ]
    assert reply.buttons[1][0].url is None and reply.buttons[1][0].callback_data == "pay:in_big"
    assert reply.text == (
        "You have 2 unpaid invoices.\n\nYou owe <b>CA$3,600.00</b> across 2 invoices."
    )


def test_a_reply_without_display_amounts_still_renders() -> None:
    """An observation from before amounts travelled under `display` still gets its buttons."""
    row = {
        "invoice_id": "in_1", "number": "F-0001", "status": "open", "due_date": "2026-09-11",
        "description": "Q3 retainer", "view_url": "https://invoice.example/in_1",
    }
    events = [
        AgentEvent(
            "observation", {"name": "my_invoices", "result": {"count": 1, "invoices": [row]}}
        ),
        AgentEvent("answer", {"text": "One invoice."}),
    ]
    reply = reply_for(events)
    assert [[b.text for b in row] for row in reply.buttons] == [["View F-0001", "Pay F-0001"]]
    assert reply.text == "One invoice."
