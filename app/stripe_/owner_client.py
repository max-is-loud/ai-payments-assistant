"""The production StripeGateway, and the only module that imports `stripe`.

Every public method maps SDK objects through `app.domain.mapping` and
translates SDK exceptions into `StripeGatewayError`s with a usable hint.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time

import stripe

from app.domain.mapping import to_customer, to_invoice, to_payment, to_refund
from app.domain.models import Customer, Invoice, Payment, Refund
from app.domain.periods import local_timezone
from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError

STRIPE_API_VERSION = "2026-08-26.dahlia"
"""Pinned so behaviour does not change when the reviewer's account default moves."""

PAGE = 100


@contextmanager
def translate_stripe_errors() -> Iterator[None]:
    """Turn Stripe SDK exceptions into gateway errors that say what to do next.

    Raises:
        StripeGatewayError: Authentication and generic API failures, with a hint.
        NotFound: `resource_missing`, the one invalid-request code callers handle.
        CardDeclined: A card declined while paying an invoice.
    """
    try:
        yield
    except stripe.AuthenticationError as exc:
        raise StripeGatewayError(
            "Stripe rejected the API key.",
            hint="Set STRIPE_SECRET_KEY in .env to your test-mode secret key (sk_test_...).",
        ) from exc
    except stripe.CardError as exc:
        raise CardDeclined(exc.user_message or "The card was declined.") from exc
    except stripe.InvalidRequestError as exc:
        if exc.code == "resource_missing":
            raise NotFound(exc.user_message or str(exc)) from exc
        raise StripeGatewayError(exc.user_message or str(exc)) from exc
    except stripe.StripeError as exc:
        raise StripeGatewayError(
            str(exc), hint="Check the Stripe dashboard logs for the request."
        ) from exc


class StripeOwnerGateway:
    """Full-account Stripe access for the owner assistant and the seed script."""

    def __init__(self, api_key: str) -> None:
        """Create a pinned-version client. Retries are left to the SDK (2 attempts)."""
        self._client = stripe.StripeClient(
            api_key, stripe_version=STRIPE_API_VERSION, max_network_retries=2
        )

    @property
    def api_version(self) -> str:
        """The pinned API version, exposed for tests and the seed report."""
        return STRIPE_API_VERSION

    @property
    def client(self) -> stripe.StripeClient:
        """The underlying SDK client; the seed script needs write calls this gateway does not."""
        return self._client

    def list_payments(self) -> list[Payment]:
        """Every attempted PaymentIntent, newest first.

        Not filtered by `created` on purpose: seeded history is dated by
        `occurred_at`, so period filtering happens in Python on the mapped result.
        """
        with translate_stripe_errors():
            page = self._client.v1.payment_intents.list(
                {"limit": PAGE, "expand": ["data.latest_charge", "data.customer"]}
            )
            mapped = [to_payment(intent) for intent in page.auto_paging_iter()]
        return [payment for payment in mapped if payment is not None]

    def get_payment(self, payment_id: str) -> Payment:
        """One PaymentIntent with its charge and customer expanded.

        Raises:
            NotFound: Unknown id, or an intent that was never attempted.
        """
        with translate_stripe_errors():
            intent = self._client.v1.payment_intents.retrieve(
                payment_id, {"expand": ["latest_charge", "customer"]}
            )
        payment = to_payment(intent)
        if payment is None:
            raise NotFound(f"{payment_id} has no payment attempt to act on.")
        return payment

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Invoices with customers expanded, optionally filtered."""
        params: dict[str, object] = {"limit": PAGE, "expand": ["data.customer"]}
        if customer_id:
            params["customer"] = customer_id
        if status:
            params["status"] = status
        with translate_stripe_errors():
            page = self._client.v1.invoices.list(params)  # type: ignore[arg-type]
            return [to_invoice(invoice) for invoice in page.auto_paging_iter()]

    def get_invoice(self, invoice_id: str) -> Invoice:
        """One invoice with its customer expanded."""
        with translate_stripe_errors():
            invoice = self._client.v1.invoices.retrieve(
                invoice_id, {"expand": ["customer"]}
            )
            return to_invoice(invoice)

    def list_customers(self) -> list[Customer]:
        """Every customer; a demo account has tens, not thousands."""
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            return [to_customer(customer) for customer in page.auto_paging_iter()]

    def get_customer(self, customer_id: str) -> Customer:
        """One customer by id."""
        with translate_stripe_errors():
            return to_customer(self._client.v1.customers.retrieve(customer_id))

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Scan customer metadata for a seed-minted Telegram token.

        A list-scan rather than Customer Search because search indexing lags
        by up to a minute — unacceptable in the reviewer's first session.
        """
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            for customer in page.auto_paging_iter():
                if (customer.get("metadata") or {}).get("telegram_bind_token") == token:
                    return to_customer(customer)
        return None

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund against the PaymentIntent; Stripe resolves the charge."""
        params: dict[str, object] = {"payment_intent": payment_id}
        if amount_cents is not None:
            params["amount"] = amount_cents
        with translate_stripe_errors():
            return to_refund(
                self._client.v1.refunds.create(params, options={"idempotency_key": idempotency_key})  # type: ignore[arg-type]
            )

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date,
        idempotency_key: str,
    ) -> Invoice:
        """Create, itemise, and finalise a send-by-email invoice.

        Three requests, each with its own derived idempotency key so a retry
        after a partial failure resumes rather than duplicates. The due date
        is the end of the given local day, which Stripe requires to be in the future.
        """
        due_at = datetime.combine(due_date, time(23, 59), tzinfo=local_timezone())
        with translate_stripe_errors():
            invoice = self._client.v1.invoices.create(
                {
                    "customer": customer_id,
                    "collection_method": "send_invoice",
                    "due_date": int(due_at.timestamp()),
                    "description": description,
                    "metadata": {"created_by": "assistant"},
                },
                options={"idempotency_key": f"{idempotency_key}:invoice"},
            )
            self._client.v1.invoice_items.create(
                {
                    "customer": customer_id,
                    "invoice": invoice.id,
                    "amount": amount_cents,
                    "currency": "usd",
                    "description": description,
                },
                options={"idempotency_key": f"{idempotency_key}:item"},
            )
            finalized = self._client.v1.invoices.finalize_invoice(
                invoice.id,
                {"expand": ["customer"]},
                options={"idempotency_key": f"{idempotency_key}:finalize"},
            )
        return to_invoice(finalized)

    def create_payment_link(
        self, *, amount_cents: int, description: str, idempotency_key: str
    ) -> str:
        """A payment link needs a Price; create an ad-hoc one with inline product data."""
        with translate_stripe_errors():
            price = self._client.v1.prices.create(
                {
                    "unit_amount": amount_cents,
                    "currency": "usd",
                    "product_data": {"name": description},
                },
                options={"idempotency_key": f"{idempotency_key}:price"},
            )
            link = self._client.v1.payment_links.create(
                {
                    "line_items": [{"price": price.id, "quantity": 1}],
                    "metadata": {"created_by": "assistant"},
                },
                options={"idempotency_key": f"{idempotency_key}:link"},
            )
        return link.url

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Charge the customer's default payment method for an open invoice."""
        with translate_stripe_errors():
            paid = self._client.v1.invoices.pay(
                invoice_id, {"expand": ["customer"]}, options={"idempotency_key": idempotency_key}
            )
        return to_invoice(paid)
