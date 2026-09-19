import { describe, expect, it } from "vitest";
import { ageOn, dateOfBirthError } from "./age";

const TODAY = "2026-09-18";

describe("dateOfBirthError", () => {
  it("accepts a 13th birthday today and refuses the day before it", () => {
    expect(dateOfBirthError("2013-09-18", TODAY)).toBe("");
    expect(dateOfBirthError("2013-09-19", TODAY)).toBe("You must be at least 13 to use PolicyPal.");
  });

  it("refuses an empty, future or implausible date", () => {
    expect(dateOfBirthError("", TODAY)).toBe("Enter your date of birth.");
    expect(dateOfBirthError("2026-09-19", TODAY)).toBe("Date of birth can't be in the future.");
    expect(dateOfBirthError("1900-01-01", TODAY)).toBe("Enter a real date of birth.");
  });
});

describe("ageOn", () => {
  it("turns over on the birthday itself", () => {
    expect(ageOn("1990-09-18", TODAY)).toBe(36);
    expect(ageOn("1990-09-19", TODAY)).toBe(35);
  });
});
