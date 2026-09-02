// The trail's error rendering: the owner reads a sentence; developer detail
// appears only when the server chose to send it (DEBUG=1 on the API).
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Trail } from "./Trail";
import type { AgentEvent } from "../api/types";

const errorFrame = (data: Record<string, unknown>): AgentEvent => ({ type: "error", data });

describe("Trail", () => {
  it("shows developer detail in a monospace block only when the server sends it", () => {
    const fields = { code: "llm_error", message: "Anthropic API error 400.", hint: "Try again." };
    const plain = render(<Trail events={[errorFrame(fields)]} />).container;
    expect(plain.querySelector(".line")?.textContent).toBe("Anthropic API error 400. — Try again.");
    expect(plain.querySelector("pre")).toBeNull();

    const detail = "Error code: 400 - {'type': 'error'}";
    const debug = render(<Trail events={[errorFrame({ ...fields, detail })]} />).container;
    expect(debug.querySelector("pre.mono")?.textContent).toBe(detail);
  });

  it("renders a failed action as a sentence with the error stamp, not a JSON block", () => {
    const failed: AgentEvent = {
      type: "observation",
      data: { name: "refund_payment", result: { error: "Stripe couldn't complete that request.", hint: "Try again." } },
    };
    const { container } = render(<Trail events={[failed]} />);
    expect(container.querySelector("pre")).toBeNull();
    expect(container.querySelector(".stamp")?.textContent).toBe("ERR");
    expect(container.querySelector(".line")?.textContent).toBe(
      "refund_payment failed: Stripe couldn't complete that request. — Try again.",
    );
  });

  it("keeps a successful observation behind a collapsible JSON block", () => {
    const ok: AgentEvent = { type: "observation", data: { name: "find_customer", result: { count: 1 } } };
    const { container } = render(<Trail events={[ok]} />);
    expect(container.querySelector(".stamp")?.textContent).toBe("OBS");
    expect(container.querySelector("details pre")?.textContent).toContain('"count": 1');
  });
});
