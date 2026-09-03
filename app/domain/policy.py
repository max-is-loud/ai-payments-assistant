"""The business rules a reviewer will look for, each defined exactly once.

Nothing else in the codebase may restate these numbers; import them.
"""

from datetime import timedelta

TELEGRAM_PAYMENT_CEILING_CENTS = 200_000
"""Payments at or above this amount are never completed by the bot; they escalate.

Cents of the account's own currency: $2,000 on a US account, CA$2,000 on a
Canadian one. The brief writes "$2,000" and nothing more, and a fixed number
of minor units keeps this an invariant with no exchange rate in it. Every
supported currency has a 1/100 minor unit (see `app.domain.currency`), so
"cents" stays accurate.
"""

BINDING_INACTIVITY = timedelta(days=14)
"""A Telegram binding unused for this long is revoked on next contact."""

MAX_AGENT_ITERATIONS = 5
"""Planner steps per turn before the loop gives up, so a confused model cannot spin."""
