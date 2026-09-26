import { describe, expect, it } from "vitest";
import { toExchanges } from "./exchanges";

const user = (id) => ({ id, role: "user" });
const assistant = (id) => ({ id, role: "assistant" });

describe("toExchanges", () => {
  it("pairs each question with the answer after it", () => {
    const [first, second] = toExchanges([user("q1"), assistant("a1"), user("q2")]);
    expect(first).toEqual({ key: "q1", question: user("q1"), answer: assistant("a1") });
    expect(second).toEqual({ key: "q2", question: user("q2"), answer: null });
  });

  it("gives an answer with no question before it an exchange of its own", () => {
    expect(toExchanges([assistant("a0"), user("q1")])).toEqual([
      { key: "a0", question: null, answer: assistant("a0") },
      { key: "q1", question: user("q1"), answer: null },
    ]);
  });

  it("keeps two questions in a row apart", () => {
    const exchanges = toExchanges([user("q1"), user("q2"), assistant("a2")]);
    expect(exchanges.map((e) => [e.key, e.answer?.id ?? null])).toEqual([
      ["q1", null],
      ["q2", "a2"],
    ]);
  });

  it("returns nothing for no messages", () => {
    expect(toExchanges([])).toEqual([]);
  });
});
