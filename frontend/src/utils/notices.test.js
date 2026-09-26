import { describe, expect, it } from "vitest";
import { splitNotices } from "./notices";

const standard =
  "Summaries of Benefits and Coverage quoted here for Covered California plans are for each plan's standard version; people who qualify for cost-sharing reductions or American Indian and Alaska Native cost sharing pay less than they show.";
const priorYear =
  "These are 2026 plans and prices; 2027 plans aren't available here yet, so check Covered California (https://www.coveredca.com/) for them.";

describe("splitNotices", () => {
  it("takes the server's notices off the front of an answer", () => {
    expect(splitNotices(`${priorYear}\n\n${standard}\n\nThe answer.\n\nMore.`)).toEqual({
      notices: [priorYear, standard],
      body: "The answer.\n\nMore.",
    });
  });

  it("leaves an answer without notices alone", () => {
    expect(splitNotices("The answer.")).toEqual({ notices: [], body: "The answer." });
  });

  it("only looks at the front: a notice-like paragraph later is the model's text", () => {
    expect(splitNotices(`The answer.\n\n${standard}`)).toEqual({ notices: [], body: `The answer.\n\n${standard}` });
  });

  it("copes with empty content", () => {
    expect(splitNotices("")).toEqual({ notices: [], body: "" });
  });
});
