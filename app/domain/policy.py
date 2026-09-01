"""The business rules a reviewer will look for, each defined exactly once.

Nothing else in the codebase may restate these numbers; import them.
"""

from datetime import timedelta

TELEGRAM_PAYMENT_CEILING_CENTS = 200_000
"""Payments at or above this amount are never completed by the bot; they escalate."""

BINDING_INACTIVITY = timedelta(days=14)
"""A Telegram binding unused for this long is revoked on next contact."""

MAX_AGENT_ITERATIONS = 5
"""Planner steps per turn before the loop gives up, so a confused model cannot spin."""
