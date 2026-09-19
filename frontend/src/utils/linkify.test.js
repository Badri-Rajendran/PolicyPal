import { describe, expect, it } from "vitest";
import { linkify } from "./linkify";

describe("linkify", () => {
  it("splits text around an https link and keeps both sides", () => {
    expect(linkify("Read it at https://example.com/sbc.pdf, then ask.")).toEqual([
      { text: "Read it at " },
      { text: "https://example.com/sbc.pdf", href: "https://example.com/sbc.pdf" },
      { text: ", then ask." },
    ]);
  });

  it("leaves text without links whole", () => {
    expect(linkify("No links here.")).toEqual([{ text: "No links here." }]);
  });

  it("links https only, never http or a script", () => {
    const text = "http://example.com javascript:alert(1) data:text/html,x";
    expect(linkify(text)).toEqual([{ text }]);
  });

  it("drops closing punctuation from the link", () => {
    expect(linkify("(see https://example.com/a).")[1]).toEqual({
      text: "https://example.com/a",
      href: "https://example.com/a",
    });
  });
});
