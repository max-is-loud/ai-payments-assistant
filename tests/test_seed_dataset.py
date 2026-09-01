"""The dataset is deterministic and contains every object the README and the demos rely on."""

from datetime import date, timedelta, timezone

from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from seed.dataset import build_dataset

TODAY = date(2026, 9, 1)
TZ = timezone(timedelta(hours=-4))


def test_dataset_is_deterministic() -> None:
    """Same seed, same objects, so the README's figures hold on the reviewer's account."""
    assert build_dataset(TODAY, tz=TZ) == build_dataset(TODAY, tz=TZ)


def test_dataset_contains_the_demo_fixtures() -> None:
    """Acme's $1,200 open invoice, a ceiling invoice, two declines, ~18 payments today.

    Maya shows up among today's successes too.
    """
    ds = build_dataset(TODAY, tz=TZ)
    names = {c.key: c.name for c in ds.customers}
    assert names["acme"] == "Acme Corp" and names["maya"] == "Maya Chen"
    assert all(c.email.endswith("@example.com") for c in ds.customers)
    today_ok = [p for p in ds.today_payments if not p.decline]
    today_declines = [p for p in ds.today_payments if p.decline]
    assert len(today_ok) == 18 and len(today_declines) == 2
    assert any(p.customer_key == "maya" for p in today_ok)
    open_acme = [i for i in ds.invoices if i.customer_key == "acme" and not i.paid]
    assert 120000 in [i.amount_cents for i in open_acme]
    assert any(i.amount_cents >= TELEGRAM_PAYMENT_CEILING_CENTS and not i.paid for i in ds.invoices)
    assert all(0 < i.due_in_days <= 30 for i in ds.invoices if not i.paid)


def test_history_is_dated_in_business_hours_over_three_weeks() -> None:
    """Historical payments carry past timestamps clustered into the working day."""
    ds = build_dataset(TODAY, tz=TZ)
    history = ds.history_payments
    assert history and all(p.occurred_at is not None for p in history)
    days_ago = {(TODAY - p.occurred_at.date()).days for p in history}  # type: ignore[union-attr]
    assert min(days_ago) == 1 and max(days_ago) == 21
    assert all(8 <= p.occurred_at.hour <= 18 for p in history)  # type: ignore[union-attr]
    yesterday = [p for p in history if (TODAY - p.occurred_at.date()).days == 1]  # type: ignore[union-attr]
    assert 8 <= len(yesterday) <= 14
