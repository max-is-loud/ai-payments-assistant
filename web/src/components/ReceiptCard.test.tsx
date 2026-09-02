// Every executed action renders the same three-column receipt: figure,
// description, status pill. The data shapes are the handlers' return values.
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReceiptCard } from "./ReceiptCard";

describe("ReceiptCard", () => {
  it("renders a refund as money out to a named customer", () => {
    const { container } = render(
      <ReceiptCard result={{ action: "refund_payment", data: {
        refund_id: "re_1", payment_id: "pi_1", amount_cents: 4500, customer_name: "Maya Chen", status: "succeeded",
      } }} />,
    );
    expect(container.querySelector(".head")?.textContent).toBe("Refund issued");
    expect(container.querySelector(".ldg-figure")?.textContent).toBe("−$45.00");
    expect(container.querySelector(".desc")?.textContent).toBe("to Maya Chen · re_1");
    expect(container.querySelector(".ldg-pill")?.textContent).toBe("succeeded");
  });

  it("renders an invoice with its number, due date, status, and hosted link", () => {
    const { container } = render(
      <ReceiptCard result={{ action: "create_invoice", data: {
        id: "in_1", number: "F-0007", customer_id: "cus_acme", customer_name: "Acme Corp", total_cents: 25000,
        amount_remaining_cents: 25000, status: "open", due_date: "2026-09-12",
        hosted_url: "https://invoice.example/in_1", description: "Consulting",
      } }} />,
    );
    expect(container.querySelector(".head")?.textContent).toBe("Invoice created");
    expect(container.querySelector(".ldg-figure")?.textContent).toBe("$250.00");
    expect(container.querySelector(".desc")?.textContent).toContain("Acme Corp · F-0007 · due Sep 12");
    expect(container.querySelector(".desc a")?.getAttribute("href")).toBe("https://invoice.example/in_1");
    expect(container.querySelector(".ldg-pill")?.textContent).toBe("open");
  });

  it("says whether the escalated customer was reached on Telegram", () => {
    const data = {
      escalation_id: "esc_1", customer_name: "Acme Corp", amount_cents: 240000, invoice_id: "in_2",
      hosted_url: "https://invoice.example/in_2", notified: true, already_approved: false,
    };
    const reached = render(<ReceiptCard result={{ action: "approve_escalation", data }} />).container;
    expect(reached.querySelector(".ldg-pill")?.textContent).toBe("notified");
    const missed = render(<ReceiptCard result={{ action: "approve_escalation", data: { ...data, notified: false } }} />).container;
    expect(missed.querySelector(".ldg-pill")?.textContent).toBe("not delivered");
    expect(missed.querySelector(".ldg-pill")?.className).toContain("out");
  });

  it("falls back to the raw result for an action it does not know", () => {
    const { container } = render(<ReceiptCard result={{ action: "something_new", data: { ok: true } }} />);
    expect(container.querySelector("pre")?.textContent).toContain('"ok": true');
  });
});
