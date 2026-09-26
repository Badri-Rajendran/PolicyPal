import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applyTheme, readTheme, useTheme } from "./useTheme";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("theme", () => {
  it("defaults to system", () => {
    expect(readTheme()).toBe("system");
  });

  it("ignores a stored value it doesn't know", () => {
    localStorage.setItem("policypal.theme", "sepia");
    expect(readTheme()).toBe("system");
  });

  it("reads a stored choice", () => {
    localStorage.setItem("policypal.theme", "dark");
    expect(readTheme()).toBe("dark");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
  });

  it("stores and applies a choice, and system clears it", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("policypal.theme")).toBe("dark");
    act(() => result.current.setTheme("system"));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("policypal.theme")).toBeNull();
    expect(result.current.theme).toBe("system");
  });

  it("applyTheme sets the attribute", () => {
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("still works when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(readTheme()).toBe("system");
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("light"));
    expect(result.current.theme).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
