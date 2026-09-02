"""Turn agent events into a Telegram reply.

Deterministic on purpose: the planner writes the sentence, but which
buttons appear and what a receipt says is decided here, in Python. Reply
text is Telegram HTML in the `app.telegram.formatting` dialect; the send
path escapes and validates it.
"""

from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardButton

from app.agent.events import AgentEvent

ERROR_TEXT = "Something went wrong on my side. Please try again in a moment."
NOT_CONNECTED_TEXT = (
    "I don't know which account you are yet. Open the link the business sent you to connect."
)


@dataclass
class Reply:
    """Text plus inline keyboard rows."""

    text: str
    buttons: list[list[InlineKeyboardButton]] = field(default_factory=list)


def _invoice_rows(events: list[AgentEvent]) -> list[list[InlineKeyboardButton]]:
    """View/Pay buttons for every open invoice seen in this turn's observations."""
    rows: list[list[InlineKeyboardButton]] = []
    seen: set[str] = set()
    for event in events:
        observed_names = ("my_balance", "my_invoices")
        if event.type != "observation" or event.data.get("name") not in observed_names:
            continue
        for invoice in event.data["result"].get("invoices", []):
            if invoice["status"] != "open" or invoice["invoice_id"] in seen:
                continue
            seen.add(invoice["invoice_id"])
            label = invoice.get("number") or invoice["invoice_id"]
            row: list[InlineKeyboardButton] = []
            if invoice.get("view_url"):
                row.append(InlineKeyboardButton(f"View {label}", url=invoice["view_url"]))
            row.append(
                InlineKeyboardButton(f"Pay {label}", callback_data=f"pay:{invoice['invoice_id']}")
            )
            rows.append(row)
    return rows


def reply_for(events: list[AgentEvent]) -> Reply:
    """The reply for a finished turn, keyed on its terminal event."""
    last = events[-1] if events else AgentEvent("error", {})
    if last.type == "confirmation":
        action_id = last.data["action_id"]
        row = [InlineKeyboardButton("Confirm", callback_data=f"confirm:{action_id}"),
               InlineKeyboardButton("Cancel", callback_data=f"cancel:{action_id}")]
        return Reply(f"{last.data['summary']}?", [row])
    if last.type == "answer":
        return Reply(last.data["text"], _invoice_rows(events))
    if last.type == "clarify":
        return Reply(last.data["question"])
    return Reply(ERROR_TEXT)


def receipt_reply(result: dict[str, Any]) -> Reply:
    """After a confirmed payment: no amount in the text, the receipt behind a button."""
    label = result.get("number") or result.get("invoice_id", "")
    rows: list[list[InlineKeyboardButton]] = []
    if result.get("receipt_url"):
        rows.append([InlineKeyboardButton("View receipt", url=result["receipt_url"])])
    text = f"Paid — thank you. Invoice <b>{label}</b> is settled; your receipt is below."
    return Reply(text, rows)
