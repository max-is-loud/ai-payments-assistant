"""Money formatting is the only place cents become a string; it carries the account's symbol."""

from app.domain.currency import USD, resolve
from app.domain.money import format_money, formatted_amounts


def test_format_money_groups_thousands_and_keeps_cents() -> None:
    """Amounts read like an invoice: thousands separators, two decimals, sign first."""
    assert format_money(120000, USD) == "$1,200.00"
    assert format_money(4500, USD) == "$45.00"
    assert format_money(-4500, USD) == "-$45.00"
    assert format_money(0, USD) == "$0.00"


def test_the_same_cents_carry_the_account_symbol() -> None:
    """A Canadian account's figures must not pose as US dollars."""
    assert format_money(120000, resolve("cad")) == "CA$1,200.00"
    assert format_money(120000, resolve("eur")) == "€1,200.00"


def test_formatted_amounts_replace_every_cents_field_for_prose() -> None:
    """The narrator copies strings; it is never handed an integer it might misread as dollars."""
    payload = {
        "amount_cents": 257800, "count": 2,
        "invoices": [{"amount_remaining_cents": 5, "number": "F-1"}],
        "largest": None,
    }
    assert formatted_amounts(payload, USD) == {
        "amount_formatted": "$2,578.00", "count": 2,
        "invoices": [{"amount_remaining_formatted": "$0.05", "number": "F-1"}],
        "largest": None,
    }


def test_formatted_amounts_use_the_account_currency() -> None:
    """The narrator on a Canadian account is handed CA$, so it cannot write $."""
    assert formatted_amounts({"total_cents": 120000}, resolve("cad")) == {
        "total_formatted": "CA$1,200.00"
    }
