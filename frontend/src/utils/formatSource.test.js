import { describe, expect, it } from "vitest";
import { formatSourceLabel, formatTime } from "./formatSource";

describe("formatSourceLabel", () => {
  it("strips the wiki_ prefix, extension, and underscores", () => {
    expect(formatSourceLabel("wiki_Health_insurance.txt")).toBe("Health insurance");
  });

  it("leaves a plain filename's words alone", () => {
    expect(formatSourceLabel("Marine_insurance.md")).toBe("Marine insurance");
  });
});

describe("formatTime", () => {
  it("formats an ISO timestamp as a short local time", () => {
    expect(formatTime("2026-01-01T15:30:00Z")).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)?/i);
  });
});
