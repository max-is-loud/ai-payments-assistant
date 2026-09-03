// The band reports the sync state honestly: the age of the numbers on the
// page, and when the last refresh failed, that it failed and how to try again.
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MastheadBand } from "./MastheadBand";

describe("MastheadBand", () => {
  it("names the failure beside the age of the figures and offers a retry", () => {
    const onRetry = vi.fn();
    const syncedAt = new Date(Date.now() - 3 * 60_000);
    const { container, getByRole } = render(
      <MastheadBand
        syncedAt={syncedAt} syncError="Couldn't reach the assistant API. Is it running?"
        onRetrySync={onRetry} theme="light" onToggleTheme={() => undefined}
      />,
    );
    expect(container.textContent).toContain("sync failed");
    expect(container.textContent).toContain("3m ago");
    fireEvent.click(getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("says synced when the last refresh worked", () => {
    const { container, queryByRole } = render(
      <MastheadBand syncedAt={new Date()} syncError={null} onRetrySync={() => undefined} theme="light" onToggleTheme={() => undefined} />,
    );
    expect(container.textContent).toContain("synced");
    expect(container.textContent).not.toContain("failed");
    expect(queryByRole("button", { name: "Retry" })).toBeNull();
  });
});
