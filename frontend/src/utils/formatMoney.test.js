import { describe, expect, it } from "vitest";
import { formatMoney } from "./formatMoney";

describe("formatMoney", () => {
  it("shows premiums to the cent and deductibles in whole dollars", () => {
    expect(formatMoney("620.15", { cents: true })).toBe("$620.15");
    expect(formatMoney("5990.00")).toBe("$5,990");
    expect(formatMoney("0.00")).toBe("$0");
  });

  it("has nothing to show for a missing amount", () => {
    expect(formatMoney(null)).toBeNull();
  });
});
