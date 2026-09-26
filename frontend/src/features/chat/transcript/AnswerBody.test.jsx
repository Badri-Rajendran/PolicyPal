import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import AnswerBody from "./AnswerBody";

const message = {
  id: "a1",
  role: "assistant",
  sources: [
    { id: "s1", source: "Sharp - Summary of Benefits - Urgent.pdf", relevance: 0.9 },
    { id: "s2", source: "wiki_Health.txt", relevance: 0.8 },
  ],
  plans: [{ hios_plan_id: "92499CA0020006", name: "Sharp Silver 70 Premier HMO" }],
};

function renderBody(content, props = {}) {
  const handlers = { onOpenSource: vi.fn(), onHoverSource: vi.fn() };
  const view = render(<AnswerBody message={message} content={content} {...handlers} {...props} />);
  return { ...view, ...handlers };
}

describe("AnswerBody", () => {
  it("renders Markdown: bold and a GFM table", () => {
    renderBody("A **bold** claim.\n\n| Plan | Copay |\n| --- | --- |\n| Sharp | $50 |");
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "$50" })).toBeInTheDocument();
  });

  it("scrolls a wide table in its own box", () => {
    const { container } = renderBody("| A | B |\n| --- | --- |\n| 1 | 2 |");
    expect(container.querySelector(".md-table-scroll")).toContainElement(screen.getByRole("table"));
  });

  it("renders raw HTML as text, never as elements", () => {
    const { container } = renderBody("Hi <script>alert(1)</script> <img src=x onerror=alert(1)>");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("<script>alert(1)</script>");
  });

  it("drops a javascript: link, leaving its text", () => {
    const { container } = renderBody("[click me](javascript:alert(1))");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(container).toHaveTextContent("click me");
  });

  it("never links anything but https", () => {
    renderBody("Try http://example.com or [this](http://example.com/x).");
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("opens an https link in a new tab, safely", () => {
    renderBody("Read [the summary](https://example.com/sbc.pdf) or https://example.org/x.");
    const [first, second] = screen.getAllByRole("link");
    expect(first).toHaveAttribute("href", "https://example.com/sbc.pdf");
    expect(first).toHaveAttribute("target", "_blank");
    expect(first).toHaveAttribute("rel", "noopener noreferrer");
    expect(first).toHaveTextContent("the summary (opens in a new tab)");
    expect(second).toHaveAttribute("href", "https://example.org/x");
  });

  it("shows an image only as its description", () => {
    const { container } = renderBody("![A chart of costs](https://tracker.example/pixel.png)");
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("A chart of costs");
  });

  it("keeps the answer's headings below the question's", () => {
    renderBody("# Costs\n\n## Detail");
    expect(screen.getByRole("heading", { name: "Costs" }).tagName).toBe("H3");
    expect(screen.getByRole("heading", { name: "Detail" }).tagName).toBe("H4");
  });

  it("turns a source marker into a seal that opens its source", async () => {
    const { onOpenSource, onHoverSource } = renderBody("It's covered.[Source: wiki_Health.txt]");
    const seal = screen.getByRole("button", { name: "Source 2" });
    await userEvent.click(seal);
    expect(onOpenSource).toHaveBeenCalledWith("s2");
    await userEvent.hover(seal);
    expect(onHoverSource).toHaveBeenLastCalledWith("s2");
    await userEvent.unhover(seal);
    expect(onHoverSource).toHaveBeenLastCalledWith(null);
  });

  it("marks the seal of the selected source", () => {
    renderBody("A[Source: wiki_Health.txt] B[Source: Sharp - Summary of Benefits - Urgent.pdf]", { selectedSourceId: "s2" });
    expect(screen.getByRole("button", { name: "Source 2" })).toHaveClass("sel");
    expect(screen.getByRole("button", { name: "Source 1" })).not.toHaveClass("sel");
  });

  it("stamps its seals only when told to", () => {
    const { container, rerender } = renderBody("A[Source: wiki_Health.txt]");
    expect(container.querySelector(".stamp")).toBeNull();
    rerender(<AnswerBody message={message} content="A[Source: wiki_Health.txt]" stamp onOpenSource={vi.fn()} />);
    expect(container.querySelector(".stamp")).not.toBeNull();
  });

  it("turns a plan marker into a plan ref with its number and name", () => {
    renderBody("The lowest is [Plan: 92499CA0020006].");
    expect(screen.getByRole("button", { name: "Plan 1, Sharp Silver 70 Premier HMO" })).toBeInTheDocument();
  });

  it("leaves an unknown plan marker as its text", () => {
    renderBody("See [Plan: 11111XX1111111].");
    expect(screen.getByText("See [Plan: 11111XX1111111].")).toBeInTheDocument();
  });
});
