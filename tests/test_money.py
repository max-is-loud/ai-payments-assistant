"""Dollar formatting is the only place cents become a string."""

from app.domain.money import dollar_strings, format_usd


def test_format_usd_groups_thousands_and_keeps_cents() -> None:
    """Amounts read like an invoice: thousands separators, two decimals, sign first."""
    assert format_usd(120000) == "$1,200.00"
    assert format_usd(4500) == "$45.00"
    assert format_usd(-4500) == "-$45.00"
    assert format_usd(0) == "$0.00"


def test_dollar_strings_replace_every_cents_field_for_prose() -> None:
    """The narrator copies strings; it is never handed an integer it might misread as dollars."""
    payload = {
        "amount_cents": 257800, "count": 2,
        "invoices": [{"amount_remaining_cents": 5, "number": "F-1"}],
        "largest": None,
    }
    assert dollar_strings(payload) == {
        "amount_usd": "$2,578.00", "count": 2,
        "invoices": [{"amount_remaining_usd": "$0.05", "number": "F-1"}],
        "largest": None,
    }
