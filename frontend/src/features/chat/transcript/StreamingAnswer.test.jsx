import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StreamingAnswer from "./StreamingAnswer";

const live = (overrides = {}) => ({ questionId: "q1", stages: [], notices: [], text: "", ...overrides });

function steps() {
  return within(screen.getByRole("list", { name: "Progress" }))
    .getAllByRole("listitem")
    .map((li) => [li.textContent, li.dataset.state]);
}

describe("StreamingAnswer", () => {
  it("is a live, busy region", () => {
    const { container } = render(<StreamingAnswer live={live()} />);
    const region = container.querySelector("[aria-live]");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveAttribute("aria-busy", "true");
  });

  it("ticks finished steps, spins the current one, and keeps writing pending", () => {
    render(<StreamingAnswer live={live({ stages: ["searching", "plans"] })} />);
    expect(steps()).toEqual([
      ["Searching the references (done)", "done"],
      ["Searching plans near you (in progress)", "current"],
      ["Writing the answer", "pending"],
    ]);
  });

  it("names every stage", () => {
    render(<StreamingAnswer live={live({ stages: ["understanding", "searching", "plans", "coverage", "writing"] })} />);
    expect(steps().map(([text]) => text)).toEqual([
      "Understanding your question (done)",
      "Searching the references (done)",
      "Searching plans near you (done)",
      "Reading Summaries of Benefits (done)",
      "Writing the answer (in progress)",
    ]);
  });

  it("ignores a stage it doesn't know", () => {
    render(<StreamingAnswer live={live({ stages: ["searching", "dreaming"] })} />);
    expect(steps().map(([, state]) => state)).toEqual(["current", "pending"]);
  });

  it("renders the text so far through Markdown, with the caret", () => {
    const { container } = render(<StreamingAnswer live={live({ stages: ["writing"], text: "It covers **imaging**" })} />);
    expect(screen.getByText("imaging").tagName).toBe("STRONG");
    expect(container.querySelector(".caret-end")).toHaveTextContent("It covers imaging");
  });

  it("hides citation markers until the answer is saved", () => {
    const { container } = render(
      <StreamingAnswer live={live({ stages: ["writing"], text: "Covered.[Source: wiki_Health.txt] See [Plan: 92499CA0020006]." })} />,
    );
    expect(container.querySelector(".caret-end")).toHaveTextContent("Covered. See .");
  });

  it("shows notices as notes", () => {
    render(<StreamingAnswer live={live({ notices: ["These are 2026 plans and prices."] })} />);
    expect(screen.getByRole("note")).toHaveTextContent("These are 2026 plans and prices.");
  });
});
