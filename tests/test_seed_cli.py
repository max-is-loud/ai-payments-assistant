"""The plain re-run's resume decision: complete, safely resumable, or stuck.

`classify_existing` is the pure decision the CLI's default (non-`--force`)
branch makes about existing seeded data; these tests exercise it directly
rather than driving the CLI, since it talks to no fake or real Stripe client.
"""

from datetime import date, timedelta, timezone

from seed.__main__ import classify_existing
from seed.dataset import build_dataset
from seed.inventory import Inventory, SeededCustomer

TODAY = date(2026, 9, 1)
TZ = timezone(timedelta(hours=-4))
DATASET = build_dataset(TODAY, tz=TZ)


def _customer(seed_run: str, seed_day: str, key: str) -> SeededCustomer:
    """A minimal seeded-customer fixture; only `seed_run` and `seed_day` drive the decision."""
    return SeededCustomer(
        id=f"cus_{key}", name=key, bind_token="tok", seed_day=seed_day, seed_run=seed_run
    )


def test_classify_existing_is_complete_when_every_object_is_seeded() -> None:
    """Every dataset customer and invoice already tagged: nothing to do."""
    inventory = Inventory(
        customers=[_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers],
        seeded_invoice_count=len(DATASET.invoices),
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("complete", None)


def test_classify_existing_resumes_a_same_day_single_run_short_of_invoices() -> None:
    """One run id, seeded today, short on invoices: safe to replay that run's keys."""
    inventory = Inventory(
        customers=[_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers],
        seeded_invoice_count=len(DATASET.invoices) - 1,
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("resume", "run-a")


def test_classify_existing_is_stuck_with_more_than_one_run_id() -> None:
    """Two run ids among the seeded customers: no single key namespace to replay."""
    half = len(DATASET.customers) // 2
    customers = [_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers[:half]] + [
        _customer("run-b", TODAY.isoformat(), c.key) for c in DATASET.customers[half:]
    ]
    inventory = Inventory(customers=customers, seeded_invoice_count=0)
    assert classify_existing(inventory, DATASET, TODAY) == ("stuck", None)


def test_classify_existing_is_stuck_when_seeded_on_an_earlier_day() -> None:
    """A day-old run's idempotency keys may already have expired; do not guess."""
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    inventory = Inventory(
        customers=[_customer("run-a", yesterday, c.key) for c in DATASET.customers],
        seeded_invoice_count=len(DATASET.invoices) - 1,
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("stuck", None)
