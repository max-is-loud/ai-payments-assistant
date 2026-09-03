"""Generate the seed dataset. Pure and deterministic; no Stripe here.

Acme Corp and Maya Chen are pinned because the brief's example commands
name them. Everything else comes from Faker under a fixed seed.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from faker import Faker

from app.domain.periods import local_timezone

AMOUNT_BUCKETS: list[tuple[tuple[int, int], int]] = [
    ((1500, 6000), 60),
    ((6000, 25000), 30),
    ((25000, 80000), 10),
]
BUSINESS_HOURS = list(range(8, 19))
HOUR_WEIGHTS = [1, 2, 4, 5, 5, 3, 4, 5, 5, 3, 2]
DESCRIPTIONS = [
    "Consulting",
    "Monthly retainer",
    "Design sprint",
    "Support plan",
    "Workshop",
    "Licence renewal",
    "Onboarding",
    "Data migration",
]
HISTORY_DAYS = 21
TODAY_SUCCESSES = 18
TODAY_DECLINES = 2


@dataclass(frozen=True)
class SeedCustomer:
    """A customer to create."""

    key: str
    name: str
    email: str


@dataclass(frozen=True)
class SeedPayment:
    """A payment attempt. `occurred_at=None` means today, with Stripe's own timestamp."""

    key: str
    customer_key: str
    amount_cents: int
    occurred_at: datetime | None
    decline: bool
    description: str


@dataclass(frozen=True)
class SeedInvoice:
    """An invoice; paid ones are marked paid out of band and dated in the past."""

    key: str
    customer_key: str
    amount_cents: int
    description: str
    due_in_days: int
    paid: bool

    @property
    def expected_status(self) -> str:
        """The Stripe status a finished seed leaves this invoice in: `paid` or `open`.

        A draft, or an open invoice that should have been paid, means the
        writer was interrupted between its steps and the seed is not done.
        """
        return "paid" if self.paid else "open"


@dataclass(frozen=True)
class Dataset:
    """Everything the seed writes."""

    today: date
    customers: list[SeedCustomer]
    payments: list[SeedPayment]
    invoices: list[SeedInvoice]

    @property
    def today_payments(self) -> list[SeedPayment]:
        """Payments created with real timestamps."""
        return [p for p in self.payments if p.occurred_at is None]

    @property
    def history_payments(self) -> list[SeedPayment]:
        """Payments carrying `demo_created_at`."""
        return [p for p in self.payments if p.occurred_at is not None]


def _slug(name: str) -> str:
    """`Maya Chen` → `maya.chen`."""
    return ".".join(part.lower() for part in name.replace(",", "").split())


def _amount(rng: random.Random) -> int:
    """Weighted amount in cents, rounded to the dollar so figures read naturally."""
    ((low, high),) = rng.choices(
        [b for b, _ in AMOUNT_BUCKETS], weights=[w for _, w in AMOUNT_BUCKETS]
    )
    return rng.randint(low // 100, high // 100) * 100


def _customers(fake: Faker) -> list[SeedCustomer]:
    """Two pinned customers plus four companies and four people."""
    pinned = [
        SeedCustomer("acme", "Acme Corp", "billing.acme@example.com"),
        SeedCustomer("maya", "Maya Chen", "maya.chen@example.com"),
    ]
    generated = [fake.company() for _ in range(4)] + [fake.name() for _ in range(4)]
    return pinned + [
        SeedCustomer(f"c{i}", name, f"{_slug(name)}@example.com")
        for i, name in enumerate(generated)
    ]


def build_dataset(today: date, seed: int = 42, tz: tzinfo | None = None) -> Dataset:
    """Build the dataset for `today`. Same inputs, same output."""
    zone = tz or local_timezone()
    Faker.seed(seed)
    fake = Faker()
    rng = random.Random(seed)
    customers = _customers(fake)
    keys = [c.key for c in customers]
    weights = [3, 3] + [1] * (
        len(keys) - 2
    )  # Acme and Maya show up more, so their stories are rich
    payments: list[SeedPayment] = []
    for days_ago in range(1, HISTORY_DAYS + 1):
        day = today - timedelta(days=days_ago)
        weekday = day.weekday() < 5
        count = 11 if days_ago == 1 else (rng.randint(5, 9) if weekday else rng.randint(1, 3))
        for n in range(count):
            hour = rng.choices(BUSINESS_HOURS, weights=HOUR_WEIGHTS)[0]
            when = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), tzinfo=zone)
            payments.append(
                SeedPayment(
                    f"h{days_ago}-{n}",
                    rng.choices(keys, weights=weights)[0],
                    _amount(rng),
                    when,
                    False,
                    rng.choice(DESCRIPTIONS),
                )
            )
    for n in range(TODAY_SUCCESSES):
        customer = "maya" if n == 0 else rng.choices(keys, weights=weights)[0]
        payments.append(
            SeedPayment(f"t{n}", customer, _amount(rng), None, False, rng.choice(DESCRIPTIONS))
        )
    for n in range(TODAY_DECLINES):
        payments.append(
            SeedPayment(f"d{n}", keys[2 + n], _amount(rng), None, True, rng.choice(DESCRIPTIONS))
        )
    invoices = [
        SeedInvoice("acme_retainer", "acme", 120000, "Q3 retainer", 10, False),
        SeedInvoice("acme_licence", "acme", 240000, "Annual licence", 21, False),
        SeedInvoice("maya_workshop", "maya", 18000, "Workshop", 5, False),
        SeedInvoice("paid_c0", "c0", 45000, "Onboarding", -20, True),
        SeedInvoice("paid_c1", "c1", 32000, "Design sprint", -12, True),
    ]
    return Dataset(today=today, customers=customers, payments=payments, invoices=invoices)
