import { describe, expect, it } from "vitest";
import { isUnreadable, sbcNote } from "./sbcStatus";

describe("sbcStatus", () => {
  it("names every status the API can send", () => {
    for (const status of ["ok", "no_link", "not_read", "blocked", "http_error", "not_pdf", "too_large", "wrong_year", "unparseable"]) {
      expect(sbcNote(status)).toMatch(/Summary of Benefits/);
    }
  });

  it("says nothing for a missing or unknown status", () => {
    expect(sbcNote(null)).toBeNull();
    expect(sbcNote(undefined)).toBeNull();
    expect(sbcNote("constructor")).toBeNull();
  });

  it("counts only known statuses other than read as unreadable", () => {
    expect(isUnreadable("blocked")).toBe(true);
    expect(isUnreadable("no_link")).toBe(true);
    expect(isUnreadable("ok")).toBe(false);
    expect(isUnreadable(null)).toBe(false);
    expect(isUnreadable("constructor")).toBe(false);
  });
});
