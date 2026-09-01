"""Detect what a previous seed left behind, and remove what Stripe allows."""

from dataclasses import dataclass, field

import stripe

from seed.report import Say


@dataclass(frozen=True)
class SeededCustomer:
    """A customer created by a previous run."""

    id: str
    name: str
    bind_token: str
    seed_day: str
    seed_run: str


@dataclass
class Inventory:
    """Seeded objects still in the account."""

    customers: list[SeededCustomer] = field(default_factory=list)
    open_invoice_ids: list[str] = field(default_factory=list)
    seeded_invoice_count: int = 0
    """Every seed-tagged invoice regardless of status, so a caller can tell an
    interrupted seed (short of invoices) from a complete one — unlike
    `open_invoice_ids`, which a finished seed's paid invoices never appear in.
    """

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

    Invoices are scanned regardless of status (not just "open"), so the
    caller can tell an interrupted seed (fewer seed-tagged invoices than the
    dataset expects) from a complete one — a finished seed's paid invoices
    are never "open", so counting only open invoices would undercount even a
    successful run.
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
                )
            )
    for invoice in client.v1.invoices.list({"limit": 100}).auto_paging_iter():
        invoice_data = invoice.to_dict()
        if (invoice_data.get("metadata") or {}).get("seed_run"):
            inventory.seeded_invoice_count += 1
            if invoice_data.get("status") == "open":
                inventory.open_invoice_ids.append(invoice.id)
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
