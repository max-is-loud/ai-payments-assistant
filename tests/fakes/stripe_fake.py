"""An in-memory StripeGateway that records every call.

Tests build a small account with `add_*`, exercise actions, and assert on
`calls` — a list of (method_name, kwargs) tuples in call order.
"""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any

from app.domain.models import Customer, Invoice, Payment, Refund
from app.stripe_.gateway import NotFound


class FakeStripeGateway:
    """Deterministic stand-in for Stripe; see module docstring."""

    def __init__(self) -> None:
        """Start with an empty account."""
        self.customers: dict[str, Customer] = {}
        self.payments: dict[str, Payment] = {}
        self.invoices: dict[str, Invoice] = {}
        self.bind_tokens: dict[str, str] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._counter = 0

    def _next(self, prefix: str) -> str:
        """Generate a predictable id like `re_1`."""
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def add_customer(self, customer_id: str, name: str, bind_token: str | None = None) -> Customer:
        """Register a customer, optionally with a Telegram bind token."""
        customer = Customer(id=customer_id, name=name, email=f"{customer_id}@example.com")
        self.customers[customer_id] = customer
        if bind_token:
            self.bind_tokens[bind_token] = customer_id
        return customer

    def add_payment(
        self,
        payment_id: str,
        customer_id: str,
        amount_cents: int,
        *,
        occurred_at: datetime | None = None,
        status: str = "succeeded",
        failure_reason: str | None = None,
    ) -> Payment:
        """Register a payment attempt."""
        customer = self.customers.get(customer_id)
        payment = Payment(
            id=payment_id, charge_id=f"ch_{payment_id}", customer_id=customer_id,
            customer_name=customer.name if customer else None, amount_cents=amount_cents,
            amount_refunded_cents=0, status=status, failure_reason=failure_reason,  # type: ignore[arg-type]
            description=None, occurred_at=occurred_at or datetime.now(UTC),
        )
        self.payments[payment_id] = payment
        return payment

    def add_invoice(
        self,
        invoice_id: str,
        customer_id: str,
        amount_cents: int,
        *,
        status: str = "open",
        due_at: datetime | None = None,
        description: str = "Services",
    ) -> Invoice:
        """Register an invoice; open invoices have the full amount remaining."""
        customer = self.customers.get(customer_id)
        invoice = Invoice(
            id=invoice_id,
            number=invoice_id.upper(),
            customer_id=customer_id,
            customer_name=customer.name if customer else None,
            total_cents=amount_cents,
            amount_remaining_cents=amount_cents if status == "open" else 0,
            status=status,
            due_at=due_at or (datetime.now(UTC) + timedelta(days=14)),
            hosted_url=f"https://invoice.example/{invoice_id}",
            description=description,
            occurred_at=datetime.now(UTC),
        )
        self.invoices[invoice_id] = invoice
        return invoice

    def _record(self, name: str, **kwargs: Any) -> None:
        """Append a call for later assertions."""
        self.calls.append((name, kwargs))

    def list_payments(self) -> list[Payment]:
        """Newest first, like Stripe."""
        self._record("list_payments")
        return sorted(self.payments.values(), key=lambda p: p.occurred_at, reverse=True)

    def get_payment(self, payment_id: str) -> Payment:
        """Lookup or NotFound."""
        self._record("get_payment", payment_id=payment_id)
        if payment_id not in self.payments:
            raise NotFound(f"No payment {payment_id}")
        return self.payments[payment_id]

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Filter by customer and/or status."""
        self._record("list_invoices", customer_id=customer_id, status=status)
        return [
            i for i in self.invoices.values()
            if (customer_id is None or i.customer_id == customer_id)
            and (status is None or i.status == status)
        ]

    def get_invoice(self, invoice_id: str) -> Invoice:
        """Lookup or NotFound."""
        self._record("get_invoice", invoice_id=invoice_id)
        if invoice_id not in self.invoices:
            raise NotFound(f"No invoice {invoice_id}")
        return self.invoices[invoice_id]

    def list_customers(self) -> list[Customer]:
        """Every registered customer."""
        self._record("list_customers")
        return list(self.customers.values())

    def get_customer(self, customer_id: str) -> Customer:
        """Lookup or NotFound."""
        self._record("get_customer", customer_id=customer_id)
        if customer_id not in self.customers:
            raise NotFound(f"No customer {customer_id}")
        return self.customers[customer_id]

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Resolve a seed-minted token."""
        self._record("find_customer_by_bind_token", token=token)
        customer_id = self.bind_tokens.get(token)
        return self.customers.get(customer_id) if customer_id else None

    def refund(
        self, payment_id: str, amount_cents: int | None, *, idempotency_key: str
    ) -> Refund:
        """Mark the payment refunded and return a receipt."""
        self._record(
            "refund",
            payment_id=payment_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
        )
        if payment_id not in self.payments:
            raise NotFound(f"No payment {payment_id}")
        payment = self.payments[payment_id]
        amount = payment.refundable_cents if amount_cents is None else amount_cents
        refunded = payment.amount_refunded_cents + amount
        status = "refunded" if refunded >= payment.amount_cents else "partially_refunded"
        self.payments[payment_id] = Payment(
            **{**payment.__dict__, "amount_refunded_cents": refunded, "status": status}
        )
        return Refund(
            id=self._next("re"),
            payment_id=payment_id,
            amount_cents=amount,
            status="succeeded",
        )

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date_type,
        idempotency_key: str,
    ) -> Invoice:
        """Create an open invoice."""
        self._record(
            "create_invoice",
            customer_id=customer_id,
            amount_cents=amount_cents,
            description=description,
            due_date=due_date,
            idempotency_key=idempotency_key,
        )
        due_at = datetime(
            due_date.year, due_date.month, due_date.day, 23, 59, tzinfo=UTC
        )
        return self.add_invoice(
            self._next("in"),
            customer_id,
            amount_cents,
            description=description,
            due_at=due_at,
        )

    def create_payment_link(
        self, *, amount_cents: int, description: str, idempotency_key: str
    ) -> str:
        """Return a fake URL."""
        self._record(
            "create_payment_link",
            amount_cents=amount_cents,
            description=description,
            idempotency_key=idempotency_key,
        )
        return f"https://buy.example/{self._next('plink')}"

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Mark paid and record a matching payment."""
        invoice = self.get_invoice(invoice_id)
        self._record("pay_invoice", invoice_id=invoice_id, idempotency_key=idempotency_key)
        paid = Invoice(**{**invoice.__dict__, "status": "paid", "amount_remaining_cents": 0})
        self.invoices[invoice_id] = paid
        self.add_payment(self._next("pi"), invoice.customer_id, invoice.total_cents)
        return paid
