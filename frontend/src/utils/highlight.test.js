import { describe, expect, it } from "vitest";
import { highlight, matches } from "./highlight";

describe("highlight", () => {
  it("marks every case-insensitive match", () => {
    expect(highlight("MRI cost vs mri covered", "mri")).toEqual([
      { text: "MRI", match: true },
      { text: " cost vs ", match: false },
      { text: "mri", match: true },
      { text: " covered", match: false },
    ]);
  });

  it("treats the query as text, not a pattern", () => {
    expect(highlight("Plan (a) vs plan a", "(a)")).toEqual([
      { text: "Plan ", match: false },
      { text: "(a)", match: true },
      { text: " vs plan a", match: false },
    ]);
  });

  it("returns the text whole for a blank query", () => {
    expect(highlight("Copay", "  ")).toEqual([{ text: "Copay", match: false }]);
  });
});

describe("matches", () => {
  it("finds a trimmed query anywhere, ignoring case", () => {
    expect(matches("Is an MRI covered?", " mri ")).toBe(true);
    expect(matches("Copay vs coinsurance", "mri")).toBe(false);
  });
});
