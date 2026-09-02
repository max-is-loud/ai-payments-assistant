"""The owner's action set, in the order the design lists them."""

from app.actions import owner_mutations as m
from app.actions import owner_reads as r
from app.agent.schema import ActionSpec, Registry


def build_owner_registry() -> Registry:
    """Everything the web assistant may do.

    Returns:
        A registry of owner actions in design order.
    """
    return Registry(
        [
            ActionSpec(
                "summarize_day",
                "Today's payment facts versus yesterday, plus open invoices",
                r.NoParams,
                r.summarize_day,
            ),
            ActionSpec(
                "query_payments",
                "List payments with totals, filtered by dates, customer, or status",
                r.QueryPaymentsParams,
                r.query_payments,
            ),
            ActionSpec(
                "compare_periods",
                "Totals for two date ranges and the change between them, computed exactly",
                r.ComparePeriodsParams,
                r.compare_periods,
            ),
            ActionSpec(
                "find_customer",
                "Find customers by name, email, or id",
                r.FindCustomerParams,
                r.find_customer,
            ),
            ActionSpec(
                "list_invoices",
                "List invoices, optionally by customer or status",
                r.ListInvoicesParams,
                r.list_invoices,
            ),
            ActionSpec(
                "create_invoice",
                "Create and send an invoice (asks for confirmation)",
                m.CreateInvoiceParams,
                m.create_invoice,
                mutation=True,
                describe=m.describe_create_invoice,
            ),
            ActionSpec(
                "refund_payment",
                "Refund a payment fully or partially (asks for confirmation)",
                m.RefundParams,
                m.refund_payment,
                mutation=True,
                describe=m.describe_refund,
            ),
            ActionSpec(
                "create_payment_link",
                "Create a shareable payment link (asks for confirmation)",
                m.PaymentLinkParams,
                m.create_payment_link,
                mutation=True,
                describe=m.describe_payment_link,
            ),
            ActionSpec(
                "list_escalations",
                "Customer requests waiting for the owner's approval",
                r.NoParams,
                r.list_escalations,
            ),
            ActionSpec(
                "approve_escalation",
                "Approve an escalated payment and send the customer a link "
                "(asks for confirmation)",
                m.ApproveEscalationParams,
                m.approve_escalation,
                mutation=True,
                describe=m.describe_approve_escalation,
            ),
        ]
    )
