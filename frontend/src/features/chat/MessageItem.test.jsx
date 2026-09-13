import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageItem from "./MessageItem";

describe("MessageItem", () => {
  it("labels a user message as You", () => {
    render(
      <MessageItem message={{ id: "1", role: "user", content: "What is a deductible?", created_at: "2026-01-01T00:00:00Z" }} />,
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("What is a deductible?")).toBeInTheDocument();
  });

  it("labels an assistant message as PolicyPal", () => {
    render(
      <MessageItem
        message={{ id: "2", role: "assistant", content: "It's the amount you pay first.", created_at: "2026-01-01T00:00:00Z" }}
      />,
    );
    expect(screen.getByText("PolicyPal")).toBeInTheDocument();
  });

  it("renders sources as a footnote list with relevance percentages", () => {
    render(
      <MessageItem
        message={{
          id: "3",
          role: "assistant",
          content: "It's the amount you pay first.",
          created_at: "2026-01-01T00:00:00Z",
          sources: [{ source: "wiki_Health_insurance.txt", chunk_id: "c1", relevance: 0.958 }],
        }}
      />,
    );
    expect(screen.getByText("Health insurance")).toBeInTheDocument();
    expect(screen.getByText("96% match")).toBeInTheDocument();
  });

  it("omits the sources section when there are none", () => {
    render(
      <MessageItem message={{ id: "4", role: "assistant", content: "Hi", created_at: "2026-01-01T00:00:00Z", sources: [] }} />,
    );
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });
});
