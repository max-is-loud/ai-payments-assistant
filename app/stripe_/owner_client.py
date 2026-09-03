"""The production StripeGateway, and the only module that imports `stripe`.

Every public method maps SDK objects through `app.domain.mapping` and
translates SDK exceptions into `StripeGatewayError`s with a usable hint.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time
from typing import Any

import stripe

from app.domain.currency import Currency, resolve
from app.domain.mapping import to_customer, to_invoice, to_payment, to_refund
from app.domain.models import Customer, Invoice, Payment, Refund
from app.domain.periods import local_timezone
from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError

STRIPE_API_VERSION = "2026-08-26.dahlia"
"""Pinned so behaviour does not change when the reviewer's account default moves."""

PAGE = 100


def _plain(obj: stripe.StripeObject) -> dict[str, Any]:
    """Convert a Stripe SDK object to a plain dict for domain mapping.

    In stripe-python 15, StripeObject is no longer a dict subclass and lacks
    .get() despite supporting __getitem__ and __contains__. Domain mapping
    functions use .get() for optional fields, so every SDK object must be
    converted via .to_dict(), which recursively transforms nested objects
    (latest_charge, customer, outcome, metadata) into plain dicts.
    """
    return obj.to_dict()


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
        # Transport and server failures word themselves for a developer; the
        # owner gets a sentence and the SDK's text rides along as detail.
        raise StripeGatewayError(
            "Stripe couldn't complete that request.",
            hint="Try again. The Stripe dashboard's request log shows what failed.",
            detail=str(exc),
        ) from exc


class StripeOwnerGateway:
    """Full-account Stripe access for the owner assistant and the seed script."""

    def __init__(self, api_key: str) -> None:
        """Create a pinned-version client. Retries are left to the SDK (2 attempts)."""
        self._api_key = api_key
        self._client = stripe.StripeClient(
            api_key, stripe_version=STRIPE_API_VERSION, max_network_retries=2
        )
        # Resolved on first use and kept: the account's currency does not
        # change within a process, and every write needs it.
        self._currency: Currency | None = None

    @property
    def api_version(self) -> str:
        """The pinned API version, exposed for tests and the seed report."""
        return STRIPE_API_VERSION

    def default_currency(self) -> Currency:
        """The currency this account settles in, read from Stripe rather than assumed.

        A customer is locked to a currency by the first invoice raised against
        it and can never be moved; payment intents and charges cannot be
        deleted at all. So an assumed currency does not fail cleanly — it
        leaves permanent objects in someone else's account. Callers ask first.

        Returns:
            The currency every write to this account must name.

        Raises:
            StripeGatewayError: The account could not be read.
            UnsupportedCurrency: The account has no minor unit to express cents
                in; see `app.domain.currency.resolve`.
        """
        if self._currency is None:
            with translate_stripe_errors():
                # `accounts.retrieve` on the service client addresses a *connected*
                # account by id; the key's own account is only reachable this way.
                account = stripe.Account.retrieve(
                    api_key=self._api_key, stripe_version=STRIPE_API_VERSION
                )
            self._currency = resolve(account.to_dict().get("default_currency") or "")
        return self._currency

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
            mapped = [to_payment(_plain(intent)) for intent in page.auto_paging_iter()]
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
        payment = to_payment(_plain(intent))
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
            return [to_invoice(_plain(invoice)) for invoice in page.auto_paging_iter()]

    def get_invoice(self, invoice_id: str) -> Invoice:
        """One invoice with its customer expanded."""
        with translate_stripe_errors():
            invoice = self._client.v1.invoices.retrieve(
                invoice_id, {"expand": ["customer"]}
            )
            return to_invoice(_plain(invoice))

    def list_customers(self) -> list[Customer]:
        """Every customer; a demo account has tens, not thousands."""
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            return [to_customer(_plain(customer)) for customer in page.auto_paging_iter()]

    def get_customer(self, customer_id: str) -> Customer:
        """One customer by id."""
        with translate_stripe_errors():
            customer = self._client.v1.customers.retrieve(customer_id)
            return to_customer(_plain(customer))

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Scan customer metadata for a seed-minted Telegram token.

        A list-scan rather than Customer Search because search indexing lags
        by up to a minute — unacceptable in the reviewer's first session.
        """
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            for customer in page.auto_paging_iter():
                data = _plain(customer)
                if (data.get("metadata") or {}).get("telegram_bind_token") == token:
                    return to_customer(data)
        return None

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund against the PaymentIntent; Stripe resolves the charge."""
        params: dict[str, object] = {"payment_intent": payment_id}
        if amount_cents is not None:
            params["amount"] = amount_cents
        with translate_stripe_errors():
            refund_obj = self._client.v1.refunds.create(
                params, options={"idempotency_key": idempotency_key}  # type: ignore[arg-type]
            )
            return to_refund(_plain(refund_obj))

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
        # Named on the invoice and on its item: Stripe rejects an item whose
        # currency differs from its invoice, and the invoice's own currency
        # falls back to the account default when it is not stated.
        currency = self.default_currency().code
        with translate_stripe_errors():
            invoice = self._client.v1.invoices.create(
                {
                    "customer": customer_id,
                    "collection_method": "send_invoice",
                    "currency": currency,
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
                    "currency": currency,
                    "description": description,
                },
                options={"idempotency_key": f"{idempotency_key}:item"},
            )
            finalized = self._client.v1.invoices.finalize_invoice(
                invoice.id,
                {"expand": ["customer"]},
                options={"idempotency_key": f"{idempotency_key}:finalize"},
            )
        return to_invoice(_plain(finalized))

    def create_payment_link(
        self, *, amount_cents: int, description: str, idempotency_key: str
    ) -> str:
        """A payment link needs a Price; create an ad-hoc one with inline product data."""
        currency = self.default_currency().code
        with translate_stripe_errors():
            price = self._client.v1.prices.create(
                {
                    "unit_amount": amount_cents,
                    "currency": currency,
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
        return to_invoice(_plain(paid))
