"""Owner actions resolve proposals with concrete details and execute with the injected key."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine

from app.actions.context import OwnerContext
from app.actions.owner_mutations import (
    ApproveEscalationParams,
    CreateInvoiceParams,
    PaymentLinkParams,
    RefundParams,
    approve_escalation,
    describe_approve_escalation,
    describe_create_invoice,
    describe_payment_link,
    describe_refund,
    refund_payment,
)
from app.actions.owner_reads import (
    ComparePeriodsParams,
    FindCustomerParams,
    QueryPaymentsParams,
    compare_periods,
    find_customer,
    query_payments,
)
from app.actions.owner_registry import build_owner_registry
from app.agent.executor import ActionError
from app.agent.schema import ProposalDetails
from app.db import escalations
from app.db.engine import session_scope
from tests.fakes.stripe_fake import FakeStripeGateway

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def account() -> FakeStripeGateway:
    """Maya paid $90 today, Acme paid $50 last week, one Acme invoice is open."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_payment("pi_maya", "cus_maya", 9000, occurred_at=NOW - timedelta(hours=1))
    fake.add_payment("pi_acme", "cus_acme", 5000, occurred_at=NOW - timedelta(days=6))
    fake.add_invoice("in_acme", "cus_acme", 120000)
    return fake


def test_refund_describe_names_customer_amount_and_date(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The confirmation card shows resolved facts, not ids."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        proposal = describe_refund(
            ctx, RefundParams(payment_id="pi_maya", amount_cents=4500)
        )
        assert proposal.summary == "Refund $45.00 to Maya Chen — $90.00 payment from Sep 01"
        with pytest.raises(ActionError, match="refundable"):
            describe_refund(
                ctx, RefundParams(payment_id="pi_maya", amount_cents=999900)
            )


def test_refund_executes_with_the_context_idempotency_key(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The key injected by execute_pending reaches Stripe; None means refund the remainder."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account,
            session=session,
            now=NOW,
            notify=lambda *_: True,
            idempotency_key="act_x",
        )
        result = refund_payment(ctx, RefundParams(payment_id="pi_maya"))
    assert result["amount_cents"] == 9000
    assert account.calls[-1] == (
        "refund",
        {
            "payment_id": "pi_maya",
            "amount_cents": None,
            "idempotency_key": "act_x",
        },
    )


def test_create_invoice_rejects_past_due_dates(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Stripe would reject it later with a worse message; catch it at proposal time."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        params = CreateInvoiceParams(
            customer_id="cus_acme",
            amount_cents=25000,
            description="Consulting",
            due_date=date(2026, 8, 1),
        )
        with pytest.raises(ActionError, match="future"):
            describe_create_invoice(ctx, params)
        ok = describe_create_invoice(
            ctx,
            CreateInvoiceParams(
                customer_id="cus_acme",
                amount_cents=25000,
                description="Consulting",
                due_date=date(2026, 9, 4),
            ),
        )
        assert ok.summary == (
            "Create a $250.00 invoice for Acme Corp due Fri Sep 04, 2026 — Consulting"
        )


def test_query_payments_filters_and_totals(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Totals are computed in Python so the planner never adds numbers itself."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        today = query_payments(
            ctx,
            QueryPaymentsParams(
                start_date=date(2026, 9, 1), end_date=date(2026, 9, 1)
            ),
        )
        assert (
            today["succeeded_count"] == 1
            and today["succeeded_total_cents"] == 9000
        )
        maya = query_payments(
            ctx, QueryPaymentsParams(customer_id="cus_maya")
        )
        assert [p["id"] for p in maya["payments"]] == ["pi_maya"]


def test_query_payments_says_when_the_list_is_cut_short(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The planner can only say "showing 1 of 2" — or ask for more — if the observation tells it."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        result = query_payments(ctx, QueryPaymentsParams(limit=1))
        assert result["matched_count"] == 2
        assert result["listed_count"] == 1
        assert len(result["payments"]) == 1


def test_find_customer_is_case_insensitive_substring(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """"maya" finds Maya Chen; the planner clarifies if several match."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        assert (
            [
                c["id"]
                for c in find_customer(
                    ctx, FindCustomerParams(query="maya")
                )["matches"]
            ]
            == ["cus_maya"]
        )


def test_approve_escalation_notifies_once_with_the_hosted_url(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Approval sends the customer a payment link; a repeat approval sends nothing."""
    sent: list[tuple[int, str, str | None]] = []
    with session_scope(engine) as session:
        esc = escalations.file(
            session,
            telegram_id=7,
            customer_id="cus_acme",
            customer_name="Acme Corp",
            invoice_id="in_acme",
            amount_cents=120000,
            reason="ceiling",
            now=NOW.replace(tzinfo=None),
        )
        esc_id = esc.id
    with session_scope(engine) as session:

        def notifier(tid: int, text: str, url: str | None) -> bool:
            """Record notification and return True."""
            sent.append((tid, text, url))
            return True

        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=notifier
        )
        assert "Acme Corp" in describe_approve_escalation(
            ctx, ApproveEscalationParams(escalation_id=esc_id)
        ).summary  # type: ignore[arg-type]
        first = approve_escalation(
            ctx, ApproveEscalationParams(escalation_id=esc_id)
        )
        second = approve_escalation(
            ctx, ApproveEscalationParams(escalation_id=esc_id)
        )
    assert first["notified"] is True and first["hosted_url"] == (
        "https://invoice.example/in_acme"
    )
    assert second["already_approved"] is True
    assert len(sent) == 1
    assert sent[0][0] == 7 and sent[0][2] == "https://invoice.example/in_acme"


def test_owner_registry_matches_the_design() -> None:
    """The action names are the spec's table, with refund_payment for refund_charge."""
    assert build_owner_registry().names() == [
        "summarize_day", "query_payments", "compare_periods", "find_customer", "list_invoices",
        "create_invoice",
        "refund_payment", "create_payment_link", "list_escalations", "approve_escalation",
    ]


def test_query_payments_with_a_range_includes_zero_filled_daily_totals(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The web app draws a per-day chart from the observation; a quiet day still gets a bar."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        week = query_payments(
            ctx, QueryPaymentsParams(start_date=date(2026, 8, 26), end_date=date(2026, 9, 1))
        )
        days = week["display"]["daily_totals"]
        assert [(d["date"], d["succeeded_total_cents"]) for d in days] == [
            ("2026-08-26", 5000), ("2026-08-27", 0), ("2026-08-28", 0), ("2026-08-29", 0),
            ("2026-08-30", 0), ("2026-08-31", 0), ("2026-09-01", 9000),
        ]
        unbounded = query_payments(ctx, QueryPaymentsParams(customer_id="cus_maya"))
        assert "display" not in unbounded


def test_describe_carries_structured_details_for_the_confirmation_card(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The card leads with the figure and the name, so they travel as fields, not only prose."""
    with session_scope(engine) as session:
        esc_id = escalations.file(
            session, telegram_id=7, customer_id="cus_acme", customer_name="Acme Corp",
            invoice_id="in_acme", amount_cents=240000, reason="ceiling",
            now=NOW.replace(tzinfo=None),
        ).id
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        refund = describe_refund(ctx, RefundParams(payment_id="pi_maya"))
        assert refund.details == ProposalDetails(
            amount_cents=9000, counterparty="Maya Chen", meta="pi_maya · paid today at 14:00"
        )
        invoice = describe_create_invoice(
            ctx,
            CreateInvoiceParams(
                customer_id="cus_acme", amount_cents=25000, description="Consulting",
                due_date=date(2026, 9, 4),
            ),
        )
        assert invoice.details == ProposalDetails(
            amount_cents=25000, counterparty="Acme Corp", meta="Consulting · due Fri Sep 04"
        )
        link = describe_payment_link(
            ctx, PaymentLinkParams(amount_cents=1500, description="Workshop")
        )
        assert link.details == ProposalDetails(
            amount_cents=1500, counterparty=None, meta="Workshop"
        )
        escalation = describe_approve_escalation(
            ctx, ApproveEscalationParams(escalation_id=esc_id)
        )
        assert escalation.details == ProposalDetails(
            amount_cents=240000, counterparty="Acme Corp",
            meta="Sends a Stripe payment link on Telegram",
        )


def test_compare_periods_computes_both_totals_and_the_change_in_python(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """The headline demo question gets an exact answer; the planner never adds up rows itself."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        result = compare_periods(
            ctx,
            ComparePeriodsParams(
                first_start_date=date(2026, 9, 1), first_end_date=date(2026, 9, 1),
                second_start_date=date(2026, 8, 26), second_end_date=date(2026, 8, 26),
            ),
        )
        # Ranges are ordered by date whatever order the planner passed them in.
        assert result["earlier"]["start_date"] == "2026-08-26"
        assert result["earlier"]["succeeded_total_cents"] == 5000
        assert result["later"]["start_date"] == "2026-09-01"
        assert result["later"]["succeeded_total_cents"] == 9000
        assert result["change_cents"] == 4000
        assert result["change_percent"] == 80.0
        display = result["display"]
        assert [d["succeeded_total_cents"] for d in display["earlier_daily_totals"]] == [5000]
        assert [d["succeeded_total_cents"] for d in display["later_daily_totals"]] == [9000]


def test_compare_periods_has_no_percentage_against_an_empty_baseline(
    engine: Engine, account: FakeStripeGateway
) -> None:
    """Dividing by an empty week is not a comparison; the change is stated in dollars only."""
    with session_scope(engine) as session:
        ctx = OwnerContext(
            gateway=account, session=session, now=NOW, notify=lambda *_: True
        )
        result = compare_periods(
            ctx,
            ComparePeriodsParams(
                first_start_date=date(2026, 8, 19), first_end_date=date(2026, 8, 25),
                second_start_date=date(2026, 8, 26), second_end_date=date(2026, 9, 1),
            ),
        )
        assert result["earlier"]["succeeded_total_cents"] == 0
        assert result["later"]["succeeded_total_cents"] == 14000
        assert result["change_cents"] == 14000
        assert result["change_percent"] is None
        assert len(result["display"]["earlier_daily_totals"]) == 7
        assert len(result["display"]["later_daily_totals"]) == 7


def test_compare_periods_rejects_a_reversed_range() -> None:
    """A range ending before it starts would total nothing silently; the planner is told."""
    with pytest.raises(ValueError, match="on or after"):
        ComparePeriodsParams(
            first_start_date=date(2026, 8, 25), first_end_date=date(2026, 8, 19),
            second_start_date=date(2026, 8, 26), second_end_date=date(2026, 9, 1),
        )
