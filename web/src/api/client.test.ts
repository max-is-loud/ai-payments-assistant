// What an error looks like by the time the owner reads it: envelope fields
// joined into a sentence, detail only when the server sent one, and transport
// failures in plain words instead of the browser's own.
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, describeError } from "./client";

describe("describeError", () => {
  it("joins message and hint, and appends detail on its own line only when present", () => {
    const plain = new ApiError(502, "llm_error", "Anthropic API error 400.", "Try again.");
    expect(describeError(plain)).toBe("Anthropic API error 400. Try again.");
    const debug = new ApiError(502, "llm_error", "Anthropic API error 400.", "Try again.", "Error code: 400");
    expect(describeError(debug)).toBe("Anthropic API error 400. Try again.\nError code: 400");
  });

  it("says the API could not be reached instead of 'Failed to fetch'", () => {
    expect(describeError(new TypeError("Failed to fetch"))).toBe("Couldn't reach the assistant API. Is it running?");
  });
});

describe("apiFetch", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("turns a response that is not our envelope into a sentence naming the status", async () => {
    vi.stubGlobal("fetch", async () => new Response("", { status: 502, statusText: "Bad Gateway" }));
    await expect(apiFetch("/api/x")).rejects.toMatchObject({
      code: "http_error",
      message: "The assistant API didn't answer (HTTP 502). Is it running?",
    });
  });

  it("reads detail from the envelope when the server includes it", async () => {
    const body = { error: { code: "internal_error", message: "Something went wrong on our side.", hint: "Try again.", detail: "RuntimeError: boom" } };
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify(body), { status: 500 }));
    await expect(apiFetch("/api/x")).rejects.toMatchObject({ code: "internal_error", detail: "RuntimeError: boom" });
  });
});
