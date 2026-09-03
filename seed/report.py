"""What the reviewer reads when the seed finishes: figures to verify, tokens to bind."""

from collections.abc import Iterable
from typing import Protocol

from app.domain.currency import Currency
from app.domain.money import format_money
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from seed.dataset import Dataset


class Say(Protocol):
    """An output sink for progress and report lines (print, or a test recorder)."""

    def __call__(self, line: str) -> None:
        """Emit one line."""
        ...


def print_report(
    dataset: Dataset,
    customers: Iterable[tuple[str, str]],
    currency: Currency,
    say: Say,
) -> None:
    """Print today's expected figures and the per-customer Telegram tokens.

    Args:
        dataset: The dataset that was written.
        customers: (name, bind_token) pairs.
        currency: The account's currency, so the figures printed here match the
            ones the app will show rather than assuming dollars.
        say: Output sink.
    """
    today_ok = [p for p in dataset.today_payments if not p.decline]
    say("")
    say("Seeded. Figures the daily summary should report today:")
    total = format_money(sum(p.amount_cents for p in today_ok), currency)
    say(f"  {len(today_ok)} successful payments totalling {total}")
    say(f"  {len([p for p in dataset.today_payments if p.decline])} declines (insufficient funds)")
    for invoice in dataset.invoices:
        if not invoice.paid:
            flag = (
                "  ← at/above the bot's ceiling, escalates"
                if invoice.amount_cents >= TELEGRAM_PAYMENT_CEILING_CENTS
                else ""
            )
            amount = format_money(invoice.amount_cents, currency)
            say(f"  open invoice: {invoice.customer_key} {amount} — {invoice.description}{flag}")
    say("")
    say(
        "Telegram binding tokens (send `/start <token>` to your bot, or open https://t.me/<bot>?start=<token>):"
    )
    for name, token in customers:
        say(f"  {name:<28} {token}")
    say("")
    say(
        "Tip: Acme Corp has both a payable invoice and one that escalates — "
        "bind Acme to see the whole loop."
    )
