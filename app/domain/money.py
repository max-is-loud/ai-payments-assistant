"""Cents-to-string formatting. The only place an amount becomes a string in Python."""

from typing import Any

from app.domain.currency import USD, Currency


def format_money(cents: int, currency: Currency) -> str:
    """Render integer cents in one account's currency, with grouping.

    Negative amounts put the sign before the symbol so refunds read the way a
    bank statement prints them.
    """
    sign = "-" if cents < 0 else ""
    units, remainder = divmod(abs(cents), 100)
    return f"{sign}{currency.symbol}{units:,}.{remainder:02d}"


def format_usd(cents: int) -> str:
    """Render integer cents as a US dollar string with grouping.

    For the callers that have not been handed the account's currency yet; they
    keep formatting as USD, which is what they assumed before it was read.
    """
    return format_money(cents, USD)


def dollar_strings(value: Any) -> Any:
    """Rewrite every `*_cents` field of a JSON-like payload as a `*_usd` dollar string.

    For payloads handed to a narrator. A model given `succeeded_total_cents:
    257800` has written "$257,800.00" beside a hero figure of $2,578.00; given
    the string, it can only copy. Dicts and lists are walked; other values and
    keys pass through unchanged.
    """
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key.endswith("_cents") and isinstance(item, int):
                rewritten[f"{key[: -len('_cents')]}_usd"] = format_usd(item)
            else:
                rewritten[key] = dollar_strings(item)
        return rewritten
    if isinstance(value, list):
        return [dollar_strings(item) for item in value]
    return value
