"""Dollar formatting is the only place cents become a string."""

from app.domain.money import format_usd


def test_format_usd_groups_thousands_and_keeps_cents() -> None:
    """Amounts read like an invoice: thousands separators, two decimals, sign first."""
    assert format_usd(120000) == "$1,200.00"
    assert format_usd(4500) == "$45.00"
    assert format_usd(-4500) == "-$45.00"
    assert format_usd(0) == "$0.00"
