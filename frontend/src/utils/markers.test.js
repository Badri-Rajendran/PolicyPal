import { describe, expect, it } from "vitest";
import { copyText, remarkMarkers, sourceNumbers } from "./markers";

const sources = [
  { id: "s1", source: "Sharp - Summary of Benefits - Urgent.pdf" },
  { id: "s2", source: "wiki_Health.txt" },
];
const plans = [{ hios_plan_id: "92499CA0020006", name: "Sharp Silver 70 Premier HMO" }];

function run(text) {
  const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: text }] }] };
  remarkMarkers({ sources, plans })(tree);
  return tree.children[0].children;
}

describe("remarkMarkers", () => {
  it("turns a source marker into a numbered seal", () => {
    const [before, seal] = run("Fifty dollars.[Source: wiki_Health.txt]");
    expect(before).toEqual({ type: "text", value: "Fifty dollars." });
    expect(seal.data).toMatchObject({ hName: "pp-seal", hProperties: { number: 2, label: "wiki_Health.txt" } });
  });

  it("splits several labels in one bracket and drops unknown ones", () => {
    const nodes = run("x [Source: Sharp - Summary of Benefits - Urgent.pdf; nope.txt; wiki_Health.txt]");
    expect(nodes.filter((n) => n.data?.hName === "pp-seal").map((n) => n.data.hProperties.number)).toEqual([1, 2]);
  });

  it("removes a source marker whose labels are all unknown", () => {
    const nodes = run("Text.[Source: nope.txt] More.");
    expect(nodes).toEqual([
      { type: "text", value: "Text." },
      { type: "text", value: " More." },
    ]);
  });

  it("turns a known plan marker into a plan ref and leaves an unknown one as text", () => {
    const nodes = run("See [Plan: 92499CA0020006] and [Plan: 11111XX1111111].");
    const ref = nodes.find((n) => n.data?.hName === "pp-plan");
    expect(ref.data.hProperties).toEqual({ position: 1, planId: "92499CA0020006" });
    expect(ref.data.hChildren).toEqual([{ type: "text", value: "Sharp Silver 70 Premier HMO" }]);
    expect(nodes.at(-1).value).toContain("[Plan: 11111XX1111111]");
  });

  it("while an answer is pending, hides plan markers it can't resolve yet", () => {
    const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: "See [Plan: X]." }] }] };
    remarkMarkers({ pending: true })(tree);
    expect(tree.children[0].children).toEqual([
      { type: "text", value: "See " },
      { type: "text", value: "." },
    ]);
  });

  it("walks into nested nodes, but leaves link text alone", () => {
    const tree = {
      type: "root",
      children: [
        { type: "list", children: [{ type: "listItem", children: [{ type: "paragraph", children: [{ type: "strong", children: [{ type: "text", value: "a[Source: wiki_Health.txt]" }] }] }] }] },
        { type: "paragraph", children: [{ type: "link", url: "https://x.test", children: [{ type: "text", value: "[Source: wiki_Health.txt]" }] }] },
      ],
    };
    remarkMarkers({ sources, plans })(tree);
    const strong = tree.children[0].children[0].children[0].children[0];
    expect(strong.children[1].data.hName).toBe("pp-seal");
    expect(tree.children[1].children[0].children[0].value).toBe("[Source: wiki_Health.txt]");
  });

  it("works with no sources or plans", () => {
    const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: "Plain." }] }] };
    remarkMarkers()(tree);
    expect(tree.children[0].children).toEqual([{ type: "text", value: "Plain." }]);
  });
});

describe("copyText", () => {
  it("writes seals as [n] and plans as names", () => {
    expect(copyText("A [Source: wiki_Health.txt] B [Plan: 92499CA0020006].", sources, plans)).toBe(
      "A [2] B Sharp Silver 70 Premier HMO.",
    );
  });

  it("writes several labels as adjacent numbers and keeps an unknown plan as it was", () => {
    expect(
      copyText("A[Source: Sharp - Summary of Benefits - Urgent.pdf; wiki_Health.txt] [Plan: X]", sources, plans),
    ).toBe("A[1][2] [Plan: X]");
  });
});

describe("sourceNumbers", () => {
  it("numbers each label by its first position", () => {
    expect([...sourceNumbers([...sources, sources[0]])]).toEqual([
      ["Sharp - Summary of Benefits - Urgent.pdf", 1],
      ["wiki_Health.txt", 2],
    ]);
  });

  it("numbers labels without gaps when one label has several passages", () => {
    // Two passages of one document are two sources with one label (_distinct).
    expect([...sourceNumbers([sources[0], { id: "s3", source: sources[0].source }, sources[1]])]).toEqual([
      ["Sharp - Summary of Benefits - Urgent.pdf", 1],
      ["wiki_Health.txt", 2],
    ]);
  });
});

describe("seal order", () => {
  it("gives each seal its place in the answer, for the stamp's stagger", () => {
    const nodes = run("A[Source: wiki_Health.txt] B[Source: Sharp - Summary of Benefits - Urgent.pdf; wiki_Health.txt]");
    expect(nodes.filter((n) => n.data?.hName === "pp-seal").map((n) => n.data.hProperties.index)).toEqual([0, 1, 2]);
  });
});
