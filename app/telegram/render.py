"""Turn agent events into a Telegram reply.

Deterministic on purpose: the planner writes the sentence, but which
buttons appear, what a receipt says, and every figure the customer reads
are decided here, in Python. Amounts come from the observation's
interface-only `display` data, which the planner is never shown, and land
on the buttons and in one total line the server writes. Reply text is
Telegram HTML in the `app.telegram.formatting` dialect; the send path
escapes and validates it.
"""

from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardButton

from app.agent.events import AgentEvent
from app.agent.schema import DISPLAY_KEY

INVOICE_ACTIONS = ("my_balance", "my_invoices")

ERROR_TEXT = "Something went wrong on my side. Please try again in a moment."
NOT_CONNECTED_TEXT = (
    "I don't know which account you are yet. Open the link the business sent you to connect."
)


@dataclass
class Reply:
    """Text plus inline keyboard rows."""

    text: str
    buttons: list[list[InlineKeyboardButton]] = field(default_factory=list)


def _invoice_observations(events: list[AgentEvent]) -> list[dict[str, Any]]:
    """The results of this turn's invoice reads, in order."""
    return [
        event.data["result"] for event in events
        if event.type == "observation" and event.data.get("name") in INVOICE_ACTIONS
    ]


def _invoice_rows(events: list[AgentEvent]) -> list[list[InlineKeyboardButton]]:
    """One button row per open invoice seen in this turn, with its amount on the button.

    Below the ceiling: View (the hosted page) and Pay. At or above it: a
    single button that names the amount and says the owner must approve;
    tapping it files or reuses the escalation. The URL is never present for
    those, because the row carries none.
    """
    rows: list[list[InlineKeyboardButton]] = []
    seen: set[str] = set()
    for result in _invoice_observations(events):
        amounts = (result.get(DISPLAY_KEY) or {}).get("invoice_amounts") or {}
        for invoice in result.get("invoices", []):
            invoice_id = invoice["invoice_id"]
            if invoice["status"] != "open" or invoice_id in seen:
                continue
            seen.add(invoice_id)
            label = invoice.get("number") or invoice_id
            amount = amounts.get(invoice_id)
            figure = f" · {amount}" if amount else ""
            pay = f"pay:{invoice_id}"
            if invoice.get("requires_owner_approval"):
                text = f"{label}{figure} · needs the owner's approval"
                rows.append([InlineKeyboardButton(text, callback_data=pay)])
                continue
            row: list[InlineKeyboardButton] = []
            if invoice.get("view_url"):
                row.append(InlineKeyboardButton(f"View {label}", url=invoice["view_url"]))
            row.append(InlineKeyboardButton(f"Pay {label}{figure}", callback_data=pay))
            rows.append(row)
    return rows


def _owed_line(events: list[AgentEvent]) -> str | None:
    """"You owe X across N invoices", from the latest balance read that carried a total."""
    for result in reversed(_invoice_observations(events)):
        total = (result.get(DISPLAY_KEY) or {}).get("owed_total")
        count = result.get("unpaid_count")
        if total is None or count is None:
            continue
        noun = "invoice" if count == 1 else "invoices"
        return f"You owe <b>{total}</b> across {count} {noun}."
    return None


def reply_for(events: list[AgentEvent]) -> Reply:
    """The reply for a finished turn, keyed on its terminal event."""
    last = events[-1] if events else AgentEvent("error", {})
    if last.type == "confirmation":
        action_id = last.data["action_id"]
        row = [InlineKeyboardButton("Confirm", callback_data=f"confirm:{action_id}"),
               InlineKeyboardButton("Cancel", callback_data=f"cancel:{action_id}")]
        return Reply(f"{last.data['summary']}?", [row])
    if last.type == "answer":
        owed = _owed_line(events)
        text = f"{last.data['text']}\n\n{owed}" if owed else last.data["text"]
        return Reply(text, _invoice_rows(events))
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
