"""The account's settlement currency, resolved from Stripe rather than assumed.

Stripe locks a customer to a currency the first time it is invoiced, and the
lock cannot be undone — nor can a `PaymentIntent` or `Charge` be deleted. So a
wrong guess does not fail cleanly: it leaves objects in the account that no
clean-up can remove, and totals that silently add two currencies together.
Every write therefore names the currency this module resolved from the account
that will receive it.
"""

from dataclasses import dataclass

ZERO_DECIMAL = frozenset({
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
})
"""Stripe currencies whose smallest unit is the whole unit.

Every amount in this codebase is an integer number of cents. In these
currencies there is no cent, so each `*_cents` field would be a hundred times
its true value. `resolve` refuses them rather than misreport money.
"""

SYMBOLS = {
    "usd": "$", "cad": "CA$", "aud": "A$", "nzd": "NZ$", "sgd": "S$", "hkd": "HK$",
    "eur": "€", "gbp": "£", "chf": "CHF ", "sek": "SEK ", "nok": "NOK ", "dkk": "DKK ",
}
"""Display symbols, matching what `Intl.NumberFormat` renders in the web app.

The dollar family is disambiguated the way the browser does it (`CA$`, not a
bare `$`), so a figure reads the same in a narrated sentence as on the page.
A currency absent from this map is still usable; it prints its ISO code.
"""


class UnsupportedCurrency(ValueError):
    """The account settles in a currency this project cannot represent."""


@dataclass(frozen=True)
class Currency:
    """One account's settlement currency.

    `code` is lowercase because that is the form Stripe reports and the form it
    requires on writes; sending back what was read avoids a case mismatch on
    the one field that cannot be corrected afterwards.
    """

    code: str
    symbol: str

    @property
    def label(self) -> str:
        """The uppercase ISO code, for report lines and error messages."""
        return self.code.upper()


def resolve(code: str) -> Currency:
    """Turn an account's `default_currency` into a Currency, or refuse it.

    Args:
        code: Stripe's `default_currency` for the account, ISO 4217.

    Returns:
        The currency every write to that account must name.

    Raises:
        UnsupportedCurrency: The account reports no currency, or one without a
            minor unit. Both are refused before anything is created, because a
            currency mistake cannot be cleaned up after the fact.
    """
    normalised = code.strip().lower()
    if not normalised:
        raise UnsupportedCurrency(
            "Stripe reported no default currency for this account. Set one in "
            "Dashboard → Settings → Payments before seeding."
        )
    if normalised in ZERO_DECIMAL:
        raise UnsupportedCurrency(
            f"This account settles in {normalised.upper()}, which has no minor unit, "
            "and this project represents every amount in cents. Use an account whose "
            "currency has two decimal places."
        )
    return Currency(normalised, SYMBOLS.get(normalised, f"{normalised.upper()} "))


USD = Currency("usd", "$")
"""What the project assumed before it read the account; still the common case."""
