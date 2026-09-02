// The confirmation card leads with the figure and the name when the server
// sent them, and still reads as a sentence when it did not (a proposal
// restored after a reload carries no details).
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Confirmation } from "../api/types";
import { ConfirmationCard } from "./ConfirmationCard";

const refund: Confirmation = {
  action_id: "act_1",
  action: "refund_payment",
  summary: "Refund $45.00 to Maya Chen — $90.00 payment from Sep 01",
  parameters: { payment_id: "pi_1", amount_cents: 4500 },
  details: { amount_cents: 4500, counterparty: "Maya Chen", meta: "Consulting · pi_1 · paid today at 09:14" },
};

const noop = () => undefined;

describe("ConfirmationCard", () => {
  it("leads with the figure, the counterparty, and the meta line", () => {
    const { container, getByRole } = render(
      <ConfirmationCard confirmation={refund} busy={false} onApprove={noop} onCancel={noop} />,
    );
    expect(container.querySelector(".ldg-figure")?.textContent).toBe("−$45.00");
    expect(container.querySelector("strong")?.textContent).toBe("Maya Chen");
    expect(container.textContent).toContain("Consulting · pi_1 · paid today at 09:14");
    expect(getByRole("button", { name: "Approve refund" })).toBeTruthy();
  });

  it("falls back to the summary sentence when there are no details", () => {
    const { container } = render(
      <ConfirmationCard confirmation={{ ...refund, details: undefined }} busy={false} onApprove={noop} onCancel={noop} />,
    );
    expect(container.querySelector(".ldg-figure")).toBeNull();
    expect(container.textContent).toContain("Refund $45.00 to Maya Chen");
  });

  it("replaces the buttons with the decision once decided", () => {
    const { container, queryByRole } = render(
      <ConfirmationCard confirmation={refund} decided="cancelled" busy={false} onApprove={noop} onCancel={noop} />,
    );
    expect(queryByRole("button")).toBeNull();
    expect(container.textContent).toContain("Cancelled");
  });

  it("calls approve and cancel from their buttons", () => {
    const onApprove = vi.fn();
    const onCancel = vi.fn();
    const { getByRole } = render(
      <ConfirmationCard confirmation={refund} busy={false} onApprove={onApprove} onCancel={onCancel} />,
    );
    fireEvent.click(getByRole("button", { name: "Approve refund" }));
    fireEvent.click(getByRole("button", { name: "Cancel" }));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
