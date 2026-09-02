// One sentence for the owner; developer detail, when the server sent it, on
// its own mono line underneath rather than run into the sentence.
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorStrip } from "./ErrorStrip";

describe("ErrorStrip", () => {
  it("separates the sentence from developer detail", () => {
    const { container } = render(<ErrorStrip>{"Anthropic API error 400. Try again.\nError code: 400"}</ErrorStrip>);
    expect(container.querySelector(".ldg-error > span")?.firstChild?.textContent).toBe("Anthropic API error 400. Try again.");
    expect(container.querySelector(".detail")?.textContent).toBe("Error code: 400");
  });

  it("has no detail line and no Retry unless given them", () => {
    const { container, queryByRole } = render(<ErrorStrip>{"Couldn't reach the assistant API. Is it running?"}</ErrorStrip>);
    expect(container.querySelector(".detail")).toBeNull();
    expect(queryByRole("button")).toBeNull();
  });

  it("offers Retry when a retry is possible", () => {
    const onRetry = vi.fn();
    const { getByRole } = render(<ErrorStrip onRetry={onRetry}>{"The assistant could not finish this turn."}</ErrorStrip>);
    fireEvent.click(getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
