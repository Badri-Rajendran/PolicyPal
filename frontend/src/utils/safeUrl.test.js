import { describe, expect, it } from "vitest";
import { safeUrl } from "./safeUrl";

describe("safeUrl", () => {
  it("keeps web addresses", () => {
    expect(safeUrl("https://example.com/sbc.pdf")).toBe("https://example.com/sbc.pdf");
    expect(safeUrl("http://example.com/sbc.pdf")).toBe("http://example.com/sbc.pdf");
  });

  it("refuses anything a browser would run or cannot open", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("JavaScript:alert(1)")).toBeNull();
    expect(safeUrl("data:text/html,<script>alert(1)</script>")).toBeNull();
    expect(safeUrl("not a url")).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});
