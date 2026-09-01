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
    assert receipt.buttons[0][0].url == "https://invoice.example/in_1"
