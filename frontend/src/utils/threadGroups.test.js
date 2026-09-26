import { describe, expect, it } from "vitest";
import { groupThreads } from "./threadGroups";

const now = new Date(2026, 8, 26, 15, 0);

function thread(id, ...date) {
  return { id, updated_at: new Date(...date).toISOString() };
}

describe("groupThreads", () => {
  it("puts each thread in its group at the date boundaries", () => {
    const groups = groupThreads(
      [
        thread("today", 2026, 8, 26, 0, 1),
        thread("yesterday", 2026, 8, 25, 23, 59),
        thread("week", 2026, 8, 19, 0, 0),
        thread("earlier", 2026, 8, 18, 23, 59),
      ],
      now,
    );
    expect(groups.map((g) => [g.label, g.threads.map((t) => t.id)])).toEqual([
      ["Today", ["today"]],
      ["Previous 7 days", ["yesterday", "week"]],
      ["Earlier", ["earlier"]],
    ]);
  });

  it("omits empty groups and keeps the order within a group", () => {
    const groups = groupThreads([thread("b", 2026, 0, 2), thread("a", 2026, 0, 3)], now);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Earlier");
    expect(groups[0].threads.map((t) => t.id)).toEqual(["b", "a"]);
  });

  it("returns nothing for no threads", () => {
    expect(groupThreads([], now)).toEqual([]);
  });
});
