"""Detect what a previous seed left behind, and remove what Stripe allows."""

from dataclasses import dataclass, field

import stripe

from seed.report import Say


@dataclass(frozen=True)
class SeededCustomer:
    """A customer created by a previous run.

    `seed_key` is the dataset key the customer was created for, so a resume
    can tell which customers already exist and keep their ids and tokens.
    """

    id: str
    name: str
    bind_token: str
    seed_day: str
    seed_run: str
    seed_key: str = ""


@dataclass(frozen=True)
class SeededInvoice:
    """A seed-tagged invoice as the account has it now: whose run, which key, what state."""

    id: str
    seed_run: str
    seed_key: str
    status: str


@dataclass
class Inventory:
    """Seeded objects still in the account."""

    customers: list[SeededCustomer] = field(default_factory=list)
    invoices: list[SeededInvoice] = field(default_factory=list)
    """Every seed-tagged invoice, whatever its status, with its run and state.

    Kept per run and per state so an interrupted seed is told apart from a
    complete one: `--force` voids open invoices but cannot delete them, so an
    older run's invoices stay in the account; and an invoice the writer was
    interrupted on exists as a draft, or as open where it should be paid, so
    counting objects would call a half-written invoice done.
    """

    @property
    def open_invoice_ids(self) -> list[str]:
        """The invoices `--clean` can void."""
        return [i.id for i in self.invoices if i.status == "open"]

    def invoice_status(self, run_id: str, seed_key: str) -> str | None:
        """The state of one run's invoice for one dataset key, or None if it was never created."""
        for invoice in self.invoices:
            if invoice.seed_run == run_id and invoice.seed_key == seed_key:
                return invoice.status
        return None

    @property
    def seed_days(self) -> set[str]:
        """Days on which customers were seeded (normally one)."""
        return {c.seed_day for c in self.customers}

    @property
    def run_ids(self) -> set[str]:
        """Run ids present among the seeded customers.

        A single value means a same-day retry can safely replay that run's
        `seed:<run_id>:<key>` idempotency keys to finish an interrupted seed.
        More than one means the account mixes runs (or a stale attempt), and
        there is no single key namespace it is safe to resume under.
        """
        return {c.seed_run for c in self.customers}


def find_seeded(client: stripe.StripeClient) -> Inventory:
    """Scan customers and invoices for `metadata.seed_run`.

    Invoices are scanned regardless of status and recorded with their run
    and state, so the caller can tell an interrupted seed (an invoice of its
    run missing, still a draft, or open where it should be paid) from a
    complete one.
    """
    inventory = Inventory()
    for customer in client.v1.customers.list({"limit": 100}).auto_paging_iter():
        # StripeObject (stripe-python 15) is not a dict and has no .get(); convert first.
        data = customer.to_dict()
        meta = data.get("metadata") or {}
        if meta.get("seed_run"):
            inventory.customers.append(
                SeededCustomer(
                    customer.id,
                    data.get("name") or "",
                    meta.get("telegram_bind_token", ""),
                    meta.get("seed_day", ""),
                    meta["seed_run"],
                    meta.get("seed_key", ""),
                )
            )
    for invoice in client.v1.invoices.list({"limit": 100}).auto_paging_iter():
        invoice_data = invoice.to_dict()
        meta = invoice_data.get("metadata") or {}
        if meta.get("seed_run"):
            inventory.invoices.append(
                SeededInvoice(
                    invoice.id, meta["seed_run"], meta.get("seed_key", ""),
                    invoice_data.get("status") or "",
                )
            )
    return inventory


def clean(client: stripe.StripeClient, inventory: Inventory, say: Say) -> None:
    """Void seeded open invoices and delete seeded customers. Charges cannot be deleted; say so."""
    for invoice_id in inventory.open_invoice_ids:
        client.v1.invoices.void_invoice(invoice_id)
        say(f"  voided {invoice_id}")
    for customer in inventory.customers:
        client.v1.customers.delete(customer.id)
        say(f"  deleted {customer.name} ({customer.id})")
    say(
        "  note: Stripe does not allow deleting charges or payment intents; seeded payments remain "
        "in the account (tagged metadata.seed_run) and still count towards history."
    )
