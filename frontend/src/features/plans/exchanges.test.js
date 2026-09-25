import { describe, expect, it } from "vitest";
import { exchangeFor } from "./exchanges";

// Mirrors tests/test_exchanges.py: both sides pin California to Covered California.
describe("exchangeFor", () => {
  it("sends California to Covered California, priced from filed rates", () => {
    expect(exchangeFor("CA")).toEqual({
      name: "Covered California",
      url: "https://www.coveredca.com/",
      filedRates: true,
    });
  });

  it("sends every other state with plans to HealthCare.gov", () => {
    for (const state of ["TX", "FL", "OK"]) {
      expect(exchangeFor(state)).toEqual({
        name: "HealthCare.gov",
        url: "https://www.healthcare.gov/see-plans/",
        filedRates: false,
      });
    }
  });

  it("falls back to HealthCare.gov for a card with no state", () => {
    expect(exchangeFor(undefined).name).toBe("HealthCare.gov");
  });
});
