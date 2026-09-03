"""A Stripe view bound to one customer.

Constructed with the id from the Telegram binding row. Every method either
passes that id to Stripe or verifies ownership before acting. No public
method accepts a customer id — see `tests/test_scoped_gateway.py`.
"""

from app.domain.currency import Currency
from app.domain.models import Customer, Invoice
from app.stripe_.gateway import NotFound, StripeGateway, StripeGatewayError


class NotYourInvoice(StripeGatewayError):
    """The invoice exists but belongs to a different customer."""


class CustomerScopedGateway:
    """The only Stripe surface the customer bot's actions can reach."""

    def __init__(self, owner: StripeGateway, customer_id: str) -> None:
        """Bind an owner gateway to a single customer id."""
        self._owner = owner
        self._customer_id = customer_id

    @property
    def customer_id(self) -> str:
        """The bound customer id (read-only)."""
        return self._customer_id

    def default_currency(self) -> Currency:
        """The account's currency; a customer's invoices are always in it."""
        return self._owner.default_currency()

    def my_customer(self) -> Customer:
        """The bound customer's record."""
        return self._owner.get_customer(self._customer_id)

    def my_invoices(self, *, status: str | None = None) -> list[Invoice]:
        """Invoices for the bound customer only; the id is supplied by us, never by input."""
        return self._owner.list_invoices(customer_id=self._customer_id, status=status)

    def my_invoice(self, invoice_id: str) -> Invoice:
        """One invoice, after proving it belongs to the bound customer.

        Raises:
            NotYourInvoice: The id does not exist or belongs to another customer's
                invoice. Raised with the same message for both cases so ids cannot
                be probed.
        """
        try:
            invoice = self._owner.get_invoice(invoice_id)
        except NotFound as exc:
            raise NotYourInvoice("No such invoice on your account.") from exc
        if invoice.customer_id != self._customer_id:
            raise NotYourInvoice("No such invoice on your account.")
        return invoice

    def pay_my_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Pay one of the bound customer's invoices with their card on file.

        The ownership check runs before any payment call, so a guessed id
        fails without touching Stripe's payment endpoint.
        """
        self.my_invoice(invoice_id)
        return self._owner.pay_invoice(invoice_id, idempotency_key=idempotency_key)
