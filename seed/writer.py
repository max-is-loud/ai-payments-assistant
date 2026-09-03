"""Create the dataset in Stripe. Every call is idempotent per (run_id, object key)."""

import secrets
from dataclasses import dataclass
from datetime import timedelta

import stripe

from app.domain.currency import Currency
from seed.dataset import Dataset, SeedPayment
from seed.report import Say

SUCCESS_CARD = "pm_card_visa"
DECLINE_CARD = "pm_card_chargeDeclinedInsufficientFunds"


@dataclass(frozen=True)
class CreatedCustomer:
    """What the report needs about a created customer."""

    key: str
    id: str
    name: str
    bind_token: str


def _opts(run_id: str, key: str) -> dict[str, str]:
    """Per-object idempotency options."""
    return {"idempotency_key": f"seed:{run_id}:{key}"}


def create_customers(
    client: stripe.StripeClient, dataset: Dataset, run_id: str, say: Say
) -> dict[str, CreatedCustomer]:
    """Create customers with a card on file and a Telegram bind token in metadata."""
    created: dict[str, CreatedCustomer] = {}
    for customer in dataset.customers:
        token = secrets.token_urlsafe(12)
        row = client.v1.customers.create(
            {
                "name": customer.name,
                "email": customer.email,
                "metadata": {
                    "seed_run": run_id,
                    "seed_key": customer.key,
                    "seed_day": dataset.today.isoformat(),
                    "telegram_bind_token": token,
                },
            },
            options=_opts(run_id, f"cus:{customer.key}"),
        )
        method = client.v1.payment_methods.attach(
            SUCCESS_CARD, {"customer": row.id}, options=_opts(run_id, f"pm:{customer.key}")
        )
        client.v1.customers.update(
            row.id, {"invoice_settings": {"default_payment_method": method.id}}
        )
        # StripeObject (stripe-python 15) is not a dict and has no .get(); convert first.
        data = row.to_dict()
        created[customer.key] = CreatedCustomer(
            customer.key, row.id, customer.name, data["metadata"]["telegram_bind_token"]
        )
        say(f"  customer {customer.name} ({row.id})")
    return created


def create_payments(
    client: stripe.StripeClient,
    payments: list[SeedPayment],
    customer_ids: dict[str, str],
    currency: Currency,
    run_id: str,
    say: Say,
) -> tuple[int, int]:
    """Create payment intents; returns (succeeded, declined). Declines raise CardError by design.

    Args:
        client: Stripe client.
        payments: The payments to create.
        customer_ids: Seed customer key to Stripe id.
        currency: The account's own currency; a payment intent created in any
            other one can never be deleted.
        run_id: Idempotency namespace for this run.
        say: Output sink.
    """
    ok = declined = 0
    for index, payment in enumerate(payments, 1):
        metadata = {
            "seed_run": run_id,
            "seed_key": payment.key,
            "seed_scope": "history" if payment.occurred_at else "today",
        }
        if payment.occurred_at:
            metadata["demo_created_at"] = payment.occurred_at.isoformat()
        params = {
            "amount": payment.amount_cents,
            "currency": currency.code,
            "customer": customer_ids[payment.customer_key],
            "payment_method": DECLINE_CARD if payment.decline else SUCCESS_CARD,
            "confirm": True,
            "off_session": True,
            "payment_method_types": ["card"],
            "description": payment.description,
            "metadata": metadata,
        }
        try:
            client.v1.payment_intents.create(params, options=_opts(run_id, f"pi:{payment.key}"))  # type: ignore[arg-type]
            ok += 1
        except stripe.CardError:
            if not payment.decline:
                raise
            declined += 1
        if index % 10 == 0 or index == len(payments):
            say(f"  payments {index}/{len(payments)}")
    return ok, declined


def create_invoices(
    client: stripe.StripeClient,
    dataset: Dataset,
    customer_ids: dict[str, str],
    currency: Currency,
    run_id: str,
    say: Say,
) -> int:
    """Create, itemise, finalise; mark historical ones paid out of band.

    Args:
        client: Stripe client.
        dataset: The dataset being written.
        customer_ids: Seed customer key to Stripe id.
        currency: The account's own currency, named on both the invoice and its
            item. Stripe rejects an invoice whose item disagrees with it, and
            the first invoice locks the customer to that currency for good.
        run_id: Idempotency namespace for this run.
        say: Output sink.

    Returns:
        How many invoices were created.
    """
    for invoice in dataset.invoices:
        metadata = {"seed_run": run_id, "seed_key": invoice.key}
        if invoice.paid:
            paid_on = dataset.today + timedelta(days=invoice.due_in_days)
            metadata["demo_created_at"] = f"{paid_on.isoformat()}T10:00:00+00:00"
        row = client.v1.invoices.create(
            {
                "customer": customer_ids[invoice.customer_key],
                "collection_method": "send_invoice",
                "currency": currency.code,
                "days_until_due": invoice.due_in_days if invoice.due_in_days > 0 else 30,
                "description": invoice.description,
                "metadata": metadata,
            },
            options=_opts(run_id, f"in:{invoice.key}"),
        )
        client.v1.invoice_items.create(
            {
                "customer": customer_ids[invoice.customer_key],
                "invoice": row.id,
                "amount": invoice.amount_cents,
                "currency": currency.code,
                "description": invoice.description,
            },
            options=_opts(run_id, f"ii:{invoice.key}"),
        )
        client.v1.invoices.finalize_invoice(row.id, options=_opts(run_id, f"fin:{invoice.key}"))
        if invoice.paid:
            client.v1.invoices.pay(
                row.id, {"paid_out_of_band": True}, options=_opts(run_id, f"pay:{invoice.key}")
            )
        say(f"  invoice {invoice.description} for {invoice.customer_key} ({row.id})")
    return len(dataset.invoices)
