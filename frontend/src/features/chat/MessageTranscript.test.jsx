import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageTranscript from "./MessageTranscript";

const messages = [
  { id: "1", role: "user", content: "What is a deductible?", created_at: "2026-01-01T00:00:00Z" },
  { id: "2", role: "assistant", content: "It's the amount you pay first.", created_at: "2026-01-01T00:00:00Z" },
];

describe("MessageTranscript", () => {
  it("shows a loading message while the thread loads", () => {
    render(<MessageTranscript messages={[]} status="loading" isSending={false} onPrompt={() => {}} />);
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();
  });

  it("shows the empty state when there are no messages", () => {
    render(<MessageTranscript messages={[]} status="ready" isSending={false} onPrompt={() => {}} />);
    expect(screen.getByRole("heading", { name: "Ask about your policy" })).toBeInTheDocument();
  });

  it("renders every message", () => {
    render(<MessageTranscript messages={messages} status="ready" isSending={false} onPrompt={() => {}} />);
    expect(screen.getByText("What is a deductible?")).toBeInTheDocument();
    expect(screen.getByText("It's the amount you pay first.")).toBeInTheDocument();
  });

  it("shows the thinking indicator while a reply is pending", () => {
    render(<MessageTranscript messages={messages} status="ready" isSending onPrompt={() => {}} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
