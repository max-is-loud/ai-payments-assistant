"""The narrow Stripe surface the rest of the application depends on.

Actions and the agent loop are written against this Protocol; tests supply
`tests.fakes.stripe_fake.FakeStripeGateway`, production supplies
`app.stripe_.owner_client.StripeOwnerGateway`.
"""

from datetime import date
from typing import Protocol

from app.domain.models import Customer, Invoice, Payment, Refund


class StripeGatewayError(RuntimeError):
    """A Stripe call failed in a way the user can act on.

    `hint` is surfaced in the API error envelope; keep it concrete.
    """

    def __init__(self, message: str, hint: str = "") -> None:
        """Store the message and an optional fix."""
        super().__init__(message)
        self.hint = hint


class NotFound(StripeGatewayError):
    """The referenced object does not exist in this account."""


class CardDeclined(StripeGatewayError):
    """The card on file was declined when paying an invoice."""


class StripeGateway(Protocol):
    """Everything the owner assistant may do to Stripe. Amounts are cents."""

    def list_payments(self) -> list[Payment]:
        """All payment attempts, newest first. Never filtered by `created`."""
        ...

    def get_payment(self, payment_id: str) -> Payment:
        """One payment by PaymentIntent id."""
        ...

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Invoices, optionally for one customer and/or one status."""
        ...

    def get_invoice(self, invoice_id: str) -> Invoice:
        """One invoice by id."""
        ...

    def list_customers(self) -> list[Customer]:
        """Every customer in the account."""
        ...

    def get_customer(self, customer_id: str) -> Customer:
        """One customer by id."""
        ...

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """The customer whose `metadata.telegram_bind_token` equals `token`, if any."""
        ...

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund a payment, fully when `amount_cents` is None."""
        ...

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date,
        idempotency_key: str,
    ) -> Invoice:
        """Create and finalise a send-by-email invoice with one line item."""
        ...

    def create_payment_link(
        self, *, amount_cents: int, description: str, idempotency_key: str
    ) -> str:
        """Create a one-off payment link and return its URL."""
        ...

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Pay an open invoice with the customer's default payment method."""
        ...
