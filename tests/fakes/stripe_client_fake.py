"""A stateful stand-in for the `stripe.StripeClient` v1 surface the seed writes through.

It keeps the objects it creates, so a listing after a crash shows what a
real account would, and it treats idempotency keys the way Stripe does: a key
seen before with the same parameters replays the original outcome (a created
object or the error the first attempt raised) without creating anything, and
a key reused with different parameters is refused. A test can also arrange a
crash after a given number of writes, to stand in for a process that dies
partway through a stage.
"""

import copy
import json
from typing import Any

import stripe

DECLINE_CARD = "pm_card_chargeDeclinedInsufficientFunds"


class Interrupted(RuntimeError):
    """The simulated crash: raised before the write it interrupts is performed."""


class FakeStripeObject:
    """The two things the seed reads off a create response: `.id` and `.to_dict()`."""

    def __init__(self, data: dict[str, Any]) -> None:
        """Wrap the stored record."""
        self._data = data

    @property
    def id(self) -> str:
        """The Stripe id."""
        return str(self._data["id"])

    def to_dict(self) -> dict[str, Any]:
        """A plain copy, as stripe-python 15 hands back."""
        return copy.deepcopy(self._data)


class _Page:
    """What `list()` returns: an object with `auto_paging_iter()`."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        """Snapshot the matching records."""
        self._items = [FakeStripeObject(item) for item in items]

    def auto_paging_iter(self) -> Any:
        """Iterate every record; pagination is a real-Stripe detail the seed never sees."""
        return iter(self._items)


class FakeStripeClient:
    """See the module docstring. Only the endpoints the seed calls exist."""

    def __init__(self) -> None:
        """An empty sandbox."""
        self.customers_store: dict[str, dict[str, Any]] = {}
        self.payment_intents: dict[str, dict[str, Any]] = {}
        self.invoices_store: dict[str, dict[str, Any]] = {}
        self.invoice_items: dict[str, dict[str, Any]] = {}
        self.attached: list[tuple[str, str]] = []
        self.writes = 0
        self.replays: list[str] = []
        self._idempotent: dict[str, tuple[str, Any]] = {}
        self._crash_at: int | None = None
        self._counter = 0
        self.v1 = _V1(self)

    def crash_after(self, writes: int) -> None:
        """Arrange for the next write numbered `writes` (counting from now) to raise."""
        self._crash_at = self.writes + writes

    def _next(self, prefix: str) -> str:
        """Predictable ids like `cus_3`."""
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def _write(
        self, endpoint: str, fingerprint: Any, options: dict[str, str] | None, perform: Any
    ) -> Any:
        """Count the write, honour a planned crash, then apply Stripe's idempotency rules.

        Raises:
            Interrupted: The planned crash landed on this write.
            stripe.InvalidRequestError: The key was used before with other parameters.
            Exception: Whatever `perform` raised, remembered for replays of the same key.
        """
        self.writes += 1
        if self._crash_at is not None and self.writes >= self._crash_at:
            self._crash_at = None
            raise Interrupted(f"process died before write #{self.writes} ({endpoint})")
        key = (options or {}).get("idempotency_key")
        signature = json.dumps([endpoint, fingerprint], sort_keys=True, default=str)
        if key and key in self._idempotent:
            seen, outcome = self._idempotent[key]
            if seen != signature:
                raise stripe.InvalidRequestError(
                    f"Keys for idempotent requests can only be used with the same parameters "
                    f"they were first used with. Key {key!r} differs.",
                    param=None, code="idempotency_key_in_use",
                )
            self.replays.append(key)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        try:
            result = perform()
        except Exception as exc:
            if key:
                self._idempotent[key] = (signature, exc)
            raise
        if key:
            self._idempotent[key] = (signature, result)
        return result


class _V1:
    """The `client.v1` namespace."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Wire the services."""
        self.customers = _Customers(client)
        self.payment_methods = _PaymentMethods(client)
        self.payment_intents = _PaymentIntents(client)
        self.invoices = _Invoices(client)
        self.invoice_items = _InvoiceItems(client)


class _Customers:
    """`client.v1.customers`."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Bind to the store."""
        self._c = client

    def create(self, params: dict[str, Any], options: dict[str, str] | None = None) -> Any:
        """Create a customer; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Store the record."""
            record = {"id": self._c._next("cus"), "object": "customer", "deleted": False, **params}
            self._c.customers_store[record["id"]] = record
            return FakeStripeObject(record)

        return self._c._write("customers.create", params, options, perform)

    def update(self, customer_id: str, params: dict[str, Any]) -> Any:
        """Merge fields into an existing customer."""

        def perform() -> FakeStripeObject:
            """Apply the update."""
            self._c.customers_store[customer_id].update(params)
            return FakeStripeObject(self._c.customers_store[customer_id])

        return self._c._write("customers.update", [customer_id, params], None, perform)

    def list(self, _params: dict[str, Any]) -> _Page:
        """Every customer not deleted."""
        return _Page([c for c in self._c.customers_store.values() if not c["deleted"]])

    def delete(self, customer_id: str) -> Any:
        """Soft-delete, as Stripe does."""

        def perform() -> FakeStripeObject:
            """Mark deleted."""
            self._c.customers_store[customer_id]["deleted"] = True
            return FakeStripeObject(self._c.customers_store[customer_id])

        return self._c._write("customers.delete", customer_id, None, perform)


class _PaymentMethods:
    """`client.v1.payment_methods`."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Bind to the store."""
        self._c = client

    def attach(
        self, method: str, params: dict[str, Any], options: dict[str, str] | None = None
    ) -> Any:
        """Attach a test card to a customer; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Record the attachment."""
            self._c.attached.append((method, params["customer"]))
            return FakeStripeObject({"id": self._c._next("pm"), "customer": params["customer"]})

        return self._c._write("payment_methods.attach", [method, params], options, perform)


class _PaymentIntents:
    """`client.v1.payment_intents`."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Bind to the store."""
        self._c = client

    def create(self, params: dict[str, Any], options: dict[str, str] | None = None) -> Any:
        """Create and confirm; the decline test card raises CardError like Stripe does.

        A declined confirmation still leaves a PaymentIntent behind, which is
        what a real account shows, so the record is stored either way.
        """

        def perform() -> FakeStripeObject:
            """Store the intent, then decline if the card says so."""
            declined = params.get("payment_method") == DECLINE_CARD
            record = {
                "id": self._c._next("pi"), "object": "payment_intent",
                "status": "requires_payment_method" if declined else "succeeded", **params,
            }
            self._c.payment_intents[record["id"]] = record
            if declined:
                raise stripe.CardError(
                    "Your card has insufficient funds.", param="payment_method",
                    code="card_declined",
                )
            return FakeStripeObject(record)

        return self._c._write("payment_intents.create", params, options, perform)


class _Invoices:
    """`client.v1.invoices`."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Bind to the store."""
        self._c = client

    def create(self, params: dict[str, Any], options: dict[str, str] | None = None) -> Any:
        """A draft invoice; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Store the draft."""
            record = {"id": self._c._next("in"), "object": "invoice", "status": "draft", **params}
            self._c.invoices_store[record["id"]] = record
            return FakeStripeObject(record)

        return self._c._write("invoices.create", params, options, perform)

    def finalize_invoice(self, invoice_id: str, options: dict[str, str] | None = None) -> Any:
        """Draft → open; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Open the invoice."""
            self._c.invoices_store[invoice_id]["status"] = "open"
            return FakeStripeObject(self._c.invoices_store[invoice_id])

        return self._c._write("invoices.finalize", invoice_id, options, perform)

    def pay(
        self, invoice_id: str, params: dict[str, Any], options: dict[str, str] | None = None
    ) -> Any:
        """Open → paid; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Settle the invoice."""
            self._c.invoices_store[invoice_id]["status"] = "paid"
            return FakeStripeObject(self._c.invoices_store[invoice_id])

        return self._c._write("invoices.pay", [invoice_id, params], options, perform)

    def void_invoice(self, invoice_id: str) -> Any:
        """Open → void."""

        def perform() -> FakeStripeObject:
            """Void the invoice."""
            self._c.invoices_store[invoice_id]["status"] = "void"
            return FakeStripeObject(self._c.invoices_store[invoice_id])

        return self._c._write("invoices.void", invoice_id, None, perform)

    def list(self, _params: dict[str, Any]) -> _Page:
        """Every invoice, whatever its status."""
        return _Page(list(self._c.invoices_store.values()))


class _InvoiceItems:
    """`client.v1.invoice_items`."""

    def __init__(self, client: FakeStripeClient) -> None:
        """Bind to the store."""
        self._c = client

    def create(self, params: dict[str, Any], options: dict[str, str] | None = None) -> Any:
        """A line on an invoice; idempotent per key."""

        def perform() -> FakeStripeObject:
            """Store the line."""
            record = {"id": self._c._next("ii"), "object": "invoiceitem", **params}
            self._c.invoice_items[record["id"]] = record
            return FakeStripeObject(record)

        return self._c._write("invoice_items.create", params, options, perform)
