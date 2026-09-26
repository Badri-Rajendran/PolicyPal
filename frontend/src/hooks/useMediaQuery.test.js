import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "./useMediaQuery";

function stubMatchMedia(initial) {
  const listeners = new Set();
  const state = { matches: initial };
  window.matchMedia = vi.fn(() => ({
    get matches() {
      return state.matches;
    },
    addEventListener: (_type, cb) => listeners.add(cb),
    removeEventListener: (_type, cb) => listeners.delete(cb),
  }));
  return {
    set(matches) {
      state.matches = matches;
      listeners.forEach((cb) => cb());
    },
    listeners,
  };
}

afterEach(() => {
  delete window.matchMedia;
});

describe("useMediaQuery", () => {
  it("is false where matchMedia is missing", () => {
    delete window.matchMedia;
    const { result } = renderHook(() => useMediaQuery("(max-width: 720px)"));
    expect(result.current).toBe(false);
  });

  it("reports whether the query matches, and follows changes", () => {
    const media = stubMatchMedia(true);
    const { result, unmount } = renderHook(() => useMediaQuery("(max-width: 720px)"));
    expect(result.current).toBe(true);
    expect(window.matchMedia).toHaveBeenCalledWith("(max-width: 720px)");
    act(() => media.set(false));
    expect(result.current).toBe(false);
    unmount();
    expect(media.listeners.size).toBe(0);
  });
});
