import { afterEach, describe, expect, it, vi } from "vitest";
import { modKey } from "./shortcutKey";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("modKey", () => {
  it("is ⌘ on a Mac", () => {
    vi.stubGlobal("navigator", { platform: "MacIntel" });
    expect(modKey()).toBe("⌘");
  });

  it("is Ctrl elsewhere", () => {
    vi.stubGlobal("navigator", { platform: "Win32" });
    expect(modKey()).toBe("Ctrl");
  });

  it("is Ctrl when the platform is unknown", () => {
    vi.stubGlobal("navigator", {});
    expect(modKey()).toBe("Ctrl");
  });
});
