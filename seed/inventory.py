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


@dataclass
class Inventory:
    """Seeded objects still in the account."""

    customers: list[SeededCustomer] = field(default_factory=list)
    open_invoice_ids: list[str] = field(default_factory=list)

    @property
    def seed_days(self) -> set[str]:
        """Days on which customers were seeded (normally one)."""
        return {c.seed_day for c in self.customers}


def find_seeded(client: stripe.StripeClient) -> Inventory:
    """Scan customers and open invoices for `metadata.seed_run`."""
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
                )
            )
    for invoice in client.v1.invoices.list({"limit": 100, "status": "open"}).auto_paging_iter():
        invoice_data = invoice.to_dict()
        if (invoice_data.get("metadata") or {}).get("seed_run"):
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
