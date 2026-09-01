"""Cents-to-dollars formatting. The only place an amount becomes a string in Python."""


def format_usd(cents: int) -> str:
    """Render integer cents as a US dollar string with grouping.

    Negative amounts put the sign before the dollar sign so refunds read the
    way a bank statement prints them.
    """
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"
