"""The plain re-run's resume decision: complete, safely resumable, or stuck.

`classify_existing` is the pure decision the CLI's default (non-`--force`)
branch makes about existing seeded data; these tests exercise it directly
rather than driving the CLI, since it talks to no fake or real Stripe client.
"""

from datetime import date, timedelta, timezone

from seed.__main__ import classify_existing
from seed.dataset import build_dataset
from seed.inventory import Inventory, SeededCustomer, SeededInvoice

TODAY = date(2026, 9, 1)
TZ = timezone(timedelta(hours=-4))
DATASET = build_dataset(TODAY, tz=TZ)


def _customer(seed_run: str, seed_day: str, key: str) -> SeededCustomer:
    """A minimal seeded-customer fixture; only `seed_run` and `seed_day` drive the decision."""
    return SeededCustomer(
        id=f"cus_{key}", name=key, bind_token="tok", seed_day=seed_day, seed_run=seed_run
    )


def _invoices(seed_run: str, count: int | None = None) -> list[SeededInvoice]:
    """The dataset's invoices as a finished run would have left them, optionally cut short."""
    expected = [
        SeededInvoice(
            id=f"in_{i.key}", seed_run=seed_run, seed_key=i.key,
            status="paid" if i.paid else "open",
        )
        for i in DATASET.invoices
    ]
    return expected if count is None else expected[:count]


def test_classify_existing_is_complete_when_every_object_is_seeded() -> None:
    """Every dataset customer and invoice already tagged: nothing to do."""
    inventory = Inventory(
        customers=[_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers],
        invoices=_invoices("run-a"),
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("complete", None)


def test_classify_existing_resumes_a_same_day_single_run_short_of_invoices() -> None:
    """One run id, seeded today, short on invoices: safe to replay that run's keys."""
    inventory = Inventory(
        customers=[_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers],
        invoices=_invoices("run-a", len(DATASET.invoices) - 1),
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("resume", "run-a")


def test_classify_existing_is_stuck_with_more_than_one_run_id() -> None:
    """Two run ids among the seeded customers: no single key namespace to replay."""
    half = len(DATASET.customers) // 2
    customers = [_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers[:half]] + [
        _customer("run-b", TODAY.isoformat(), c.key) for c in DATASET.customers[half:]
    ]
    inventory = Inventory(customers=customers, invoices=[])
    assert classify_existing(inventory, DATASET, TODAY) == ("stuck", None)


def test_classify_existing_is_stuck_when_seeded_on_an_earlier_day() -> None:
    """A day-old run's idempotency keys may already have expired; do not guess."""
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    inventory = Inventory(
        customers=[_customer("run-a", yesterday, c.key) for c in DATASET.customers],
        invoices=_invoices("run-a", len(DATASET.invoices) - 1),
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("stuck", None)


def test_classify_existing_ignores_another_runs_invoices() -> None:
    """Voided invoices left by `--force` belong to the old run and prove nothing about this one."""
    inventory = Inventory(
        customers=[_customer("run-b", TODAY.isoformat(), c.key) for c in DATASET.customers],
        invoices=_invoices("run-a"),
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("resume", "run-b")


def test_classify_existing_resumes_when_customers_are_short_too() -> None:
    """A crash mid-customers leaves fewer than the dataset expects; that is a resume as well."""
    inventory = Inventory(
        customers=[_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers[:3]],
        invoices=[],
    )
    assert classify_existing(inventory, DATASET, TODAY) == ("resume", "run-a")


def test_classify_existing_resumes_when_an_invoice_is_not_in_its_expected_state() -> None:
    """Every invoice object exists, but one is a draft and one paid one is still open: not done."""
    customers = [_customer("run-a", TODAY.isoformat(), c.key) for c in DATASET.customers]
    draft = _invoices("run-a")
    draft[-1] = SeededInvoice(
        id=draft[-1].id, seed_run="run-a", seed_key=draft[-1].seed_key, status="draft"
    )
    assert classify_existing(Inventory(customers=customers, invoices=draft), DATASET, TODAY) == (
        "resume", "run-a",
    )
    unpaid = _invoices("run-a")
    paid_index = next(i for i, inv in enumerate(DATASET.invoices) if inv.paid)
    unpaid[paid_index] = SeededInvoice(
        id=unpaid[paid_index].id, seed_run="run-a", seed_key=unpaid[paid_index].seed_key,
        status="open",
    )
    assert classify_existing(Inventory(customers=customers, invoices=unpaid), DATASET, TODAY) == (
        "resume", "run-a",
    )
