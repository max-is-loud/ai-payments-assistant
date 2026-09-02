"""One Stripe listing serves every read for a short while; the process's own writes clear it."""

import threading
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.models import Payment
from app.stripe_.cached_gateway import CachedGateway
from tests.fakes.stripe_fake import FakeStripeGateway

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


class Clock:
    """A clock the test advances by hand."""

    def __init__(self) -> None:
        """Start at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Monotonic seconds, as `time.monotonic` would give."""
        return self.now


def _account() -> FakeStripeGateway:
    """Two customers, one payment, one open invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_payment("pi_1", "cus_maya", 9000, occurred_at=NOW - timedelta(hours=1))
    fake.add_invoice("in_1", "cus_acme", 120000)
    return fake


def _count(fake: FakeStripeGateway, name: str) -> int:
    """How many times the fake saw a call."""
    return sum(1 for called, _ in fake.calls if called == name)


@pytest.fixture
def world() -> tuple[CachedGateway, FakeStripeGateway, Clock]:
    """A cached gateway over the fake with a 20-second TTL on a hand-driven clock."""
    fake = _account()
    clock = Clock()
    return CachedGateway(fake, ttl_seconds=20, clock=clock), fake, clock


def test_repeated_listings_within_the_ttl_reach_stripe_once(
    world: tuple[CachedGateway, FakeStripeGateway, Clock],
) -> None:
    """Three dashboard reads on one page load are one Stripe listing, not three."""
    cached, fake, clock = world
    first = cached.list_payments()
    assert cached.list_payments() == first
    assert cached.list_customers() == cached.list_customers()
    assert _count(fake, "list_payments") == 1
    assert _count(fake, "list_customers") == 1
    clock.now += 21
    cached.list_payments()
    assert _count(fake, "list_payments") == 2


def test_invoice_listings_are_cached_per_filter(
    world: tuple[CachedGateway, FakeStripeGateway, Clock],
) -> None:
    """Open invoices and one customer's invoices are different questions."""
    cached, fake, _ = world
    cached.list_invoices(status="open")
    cached.list_invoices(status="open")
    cached.list_invoices(customer_id="cus_acme")
    assert _count(fake, "list_invoices") == 2


def test_the_processs_own_writes_clear_only_what_they_change(
    world: tuple[CachedGateway, FakeStripeGateway, Clock],
) -> None:
    """A refund changes payments, paying an invoice changes both, customers never change here."""
    cached, fake, _ = world
    cached.list_payments()
    cached.list_invoices(status="open")
    cached.list_customers()

    cached.refund("pi_1", 1000, idempotency_key="k1")
    cached.list_payments()
    cached.list_invoices(status="open")
    assert _count(fake, "list_payments") == 2
    assert _count(fake, "list_invoices") == 1

    cached.pay_invoice("in_1", idempotency_key="k2")
    cached.list_payments()
    cached.list_invoices(status="open")
    assert _count(fake, "list_payments") == 3
    assert _count(fake, "list_invoices") == 2

    cached.create_invoice(
        customer_id="cus_acme", amount_cents=500, description="Workshop",
        due_date=date(2026, 9, 30), idempotency_key="k3",
    )
    cached.list_invoices(status="open")
    cached.list_payments()
    assert _count(fake, "list_invoices") == 3
    assert _count(fake, "list_payments") == 3

    cached.list_customers()
    assert _count(fake, "list_customers") == 1


def test_single_object_reads_are_never_cached(
    world: tuple[CachedGateway, FakeStripeGateway, Clock],
) -> None:
    """A confirmation resolves the payment it is about to refund from Stripe, every time."""
    cached, fake, _ = world
    cached.get_payment("pi_1")
    cached.get_payment("pi_1")
    assert _count(fake, "get_payment") == 2


def test_concurrent_misses_wait_for_one_fetch() -> None:
    """Three requests arriving together during a cold cache produce one listing."""

    class SlowFake(FakeStripeGateway):
        """A fake whose listing takes long enough for the other threads to arrive."""

        def list_payments(self) -> list[Payment]:
            """Sleep, then list."""
            time.sleep(0.2)
            return super().list_payments()

    fake = SlowFake()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_payment("pi_1", "cus_maya", 9000, occurred_at=NOW)
    cached = CachedGateway(fake, ttl_seconds=20, clock=time.monotonic)
    threads = [threading.Thread(target=cached.list_payments) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert _count(fake, "list_payments") == 1
