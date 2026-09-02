"""A gateway that shares one Stripe listing across the reads that arrive together.

Period filtering cannot be pushed to Stripe — seeded history is dated by
metadata, not `created` — so every summary, chart, and planner read lists the
whole account, about 6.5 seconds at demo scale. The owner's page issues three
such reads on load and two every poll, and a planner turn repeats it per step.
This wrapper answers them all from one listing for a short while, and forgets
that listing the moment this process changes what it describes.

Staleness is bounded. Entries expire after `ttl_seconds`, kept below the web
app's 30-second poll so a poll never serves numbers older than one TTL. Writes
made by the other process (the bot paying an invoice) are seen after the TTL
rather than instantly; the demo script already promises "on its next refresh".
"""

import logging
import threading
import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.models import Customer, Invoice, Payment, Refund
from app.stripe_.gateway import StripeGateway

log = logging.getLogger(__name__)

# Below the web app's poll interval (REFRESH_MS in web/src/state/useDashboard.ts).
DEFAULT_TTL_SECONDS = 20.0

PAYMENTS = "payments"
INVOICES = "invoices"
CUSTOMERS = "customers"

Key = tuple[Hashable, ...]


@dataclass
class _Entry:
    """A cached listing and the clock reading at which it stops being trusted."""

    value: Any
    expires_at: float


class CachedGateway:
    """Delegates every call to `inner`; the three listings are cached per argument set.

    Single-object reads (`get_*`) always go to Stripe: a confirmation resolves
    the exact payment it is about to refund, and that must be current.
    """

    def __init__(
        self,
        inner: StripeGateway,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Wrap `inner`; `clock` is injectable so tests can move time by hand."""
        self._inner = inner
        self._ttl = ttl_seconds
        self._clock = clock
        self._entries: dict[Key, _Entry] = {}
        # `_guard` protects the two dicts; each key's own lock makes concurrent
        # misses wait for a single fetch instead of each calling Stripe.
        self._guard = threading.Lock()
        self._locks: dict[Key, threading.Lock] = {}

    def _cached(self, key: Key, fetch: Callable[[], Any]) -> Any:
        """The value for `key`, fetched once when missing or expired."""
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            with self._guard:
                entry = self._entries.get(key)
                if entry is not None and entry.expires_at > self._clock():
                    return entry.value
            value = fetch()
            with self._guard:
                self._entries[key] = _Entry(value, self._clock() + self._ttl)
            return value

    def _forget(self, *kinds: str) -> None:
        """Drop every cached listing of the given kinds after a write changed them."""
        with self._guard:
            for key in [key for key in self._entries if key[0] in kinds]:
                del self._entries[key]

    def list_payments(self) -> list[Payment]:
        """Every payment attempt, from the shared listing."""
        return self._cached((PAYMENTS,), self._inner.list_payments)

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Invoices for one filter combination, cached separately per combination."""
        return self._cached(
            (INVOICES, customer_id, status),
            lambda: self._inner.list_invoices(customer_id=customer_id, status=status),
        )

    def list_customers(self) -> list[Customer]:
        """Every customer; nothing this process does changes them."""
        return self._cached((CUSTOMERS,), self._inner.list_customers)

    def get_payment(self, payment_id: str) -> Payment:
        """Always fresh."""
        return self._inner.get_payment(payment_id)

    def get_invoice(self, invoice_id: str) -> Invoice:
        """Always fresh."""
        return self._inner.get_invoice(invoice_id)

    def get_customer(self, customer_id: str) -> Customer:
        """Always fresh."""
        return self._inner.get_customer(customer_id)

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Always fresh; binding happens once and must not miss a just-seeded token."""
        return self._inner.find_customer_by_bind_token(token)

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund, then forget the payment listing the refund just changed."""
        refund = self._inner.refund(payment_id, amount_cents, idempotency_key=idempotency_key)
        self._forget(PAYMENTS)
        return refund

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date,
        idempotency_key: str,
    ) -> Invoice:
        """Create the invoice, then forget invoice listings."""
        invoice = self._inner.create_invoice(
            customer_id=customer_id, amount_cents=amount_cents, description=description,
            due_date=due_date, idempotency_key=idempotency_key,
        )
        self._forget(INVOICES)
        return invoice

    def create_payment_link(
        self, *, amount_cents: int, description: str, idempotency_key: str
    ) -> str:
        """A payment link changes nothing that is listed."""
        return self._inner.create_payment_link(
            amount_cents=amount_cents, description=description, idempotency_key=idempotency_key
        )

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Paying creates a payment and closes an invoice: both listings are forgotten."""
        invoice = self._inner.pay_invoice(invoice_id, idempotency_key=idempotency_key)
        self._forget(PAYMENTS, INVOICES)
        return invoice


def warm_in_background(gateway: StripeGateway) -> threading.Thread:
    """Fetch the listings the first page reads, off the request path.

    A cold cache makes the first visitor after `make dev` pay one full Stripe
    listing. Fetching it in a daemon thread while the server finishes starting
    means the page that arrives a few seconds later finds the cache warm. Any
    failure is logged and swallowed: the first request then fetches for itself,
    and Stripe being unreachable at startup never takes the API down.

    Returns:
        The started thread, so a caller (or a test) can wait for it.
    """

    def run() -> None:
        """Populate the two listings the dashboard reads on load."""
        try:
            gateway.list_payments()
            gateway.list_invoices(status="open")
        except Exception:  # noqa: BLE001 — startup must not depend on Stripe answering
            log.warning(
                "Stripe cache warm-up failed; the first request will fetch directly", exc_info=True
            )

    thread = threading.Thread(target=run, name="stripe-cache-warm-up", daemon=True)
    thread.start()
    return thread
