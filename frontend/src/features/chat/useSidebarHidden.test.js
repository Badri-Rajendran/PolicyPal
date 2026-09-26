import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSidebarHidden } from "./useSidebarHidden";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useSidebarHidden", () => {
  it("starts shown", () => {
    const { result } = renderHook(() => useSidebarHidden());
    expect(result.current[0]).toBe(false);
  });

  it("remembers a hidden sidebar per browser, and forgets it when shown", () => {
    const { result } = renderHook(() => useSidebarHidden());
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem("policypal.sidebar")).toBe("hidden");
    expect(renderHook(() => useSidebarHidden()).result.current[0]).toBe(true);

    act(() => result.current[1](false));
    expect(localStorage.getItem("policypal.sidebar")).toBeNull();
  });

  it("still works when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    const { result } = renderHook(() => useSidebarHidden());
    expect(result.current[0]).toBe(false);
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
  });
});
