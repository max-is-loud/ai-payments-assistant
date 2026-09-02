// Text that has already arrived is revealed over a bounded duration, one
// tick at a time; reduced-motion users get all of it at once.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTypewriter } from "./useTypewriter";

describe("useTypewriter", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reveals the text progressively and reports done at the end", () => {
    const { result } = renderHook(() => useTypewriter("A strong Wednesday.", true, 1000));
    expect(result.current.shown).toBe(0);
    expect(result.current.done).toBe(false);
    act(() => vi.advanceTimersByTime(500));
    expect(result.current.shown).toBeGreaterThan(0);
    expect(result.current.shown).toBeLessThan(19);
    act(() => vi.advanceTimersByTime(600));
    expect(result.current.shown).toBe(19);
    expect(result.current.done).toBe(true);
  });

  it("waits its turn while inactive, and shows nothing for text that has not arrived", () => {
    const { result, rerender } = renderHook(
      ({ text, active }: { text: string | null; active: boolean }) => useTypewriter(text, active, 1000),
      { initialProps: { text: null as string | null, active: true } },
    );
    expect(result.current).toEqual({ shown: 0, done: false });
    rerender({ text: "Later.", active: false });
    act(() => vi.advanceTimersByTime(2000));
    expect(result.current.shown).toBe(0);
    rerender({ text: "Later.", active: true });
    act(() => vi.advanceTimersByTime(1100));
    expect(result.current).toEqual({ shown: 6, done: true });
  });

  it("is done at once for an empty aside, so the lede can start", () => {
    const { result } = renderHook(() => useTypewriter("", true, 1000));
    expect(result.current.done).toBe(true);
  });

  it("shows everything immediately when the reader prefers reduced motion", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce") }));
    const { result } = renderHook(() => useTypewriter("A strong Wednesday.", true, 1000));
    expect(result.current).toEqual({ shown: 19, done: true });
  });
});
