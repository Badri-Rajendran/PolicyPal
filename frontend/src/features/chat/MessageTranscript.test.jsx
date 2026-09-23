import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
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

  it("reports a failed load instead of the empty state", () => {
    render(
      <MessageTranscript
        messages={[]}
        status="error"
        error="Something went wrong."
        isSending={false}
        onPrompt={() => {}}
        onRetry={() => {}}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
    expect(screen.queryByRole("heading", { name: "Ask about your policy" })).not.toBeInTheDocument();
  });

  it("falls back to its own wording when the failure carries no message", () => {
    render(
      <MessageTranscript messages={[]} status="error" error="" isSending={false} onPrompt={() => {}} onRetry={() => {}} />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("This conversation couldn't be loaded.");
  });

  it("retries the load when asked", async () => {
    const onRetry = vi.fn();
    render(
      <MessageTranscript
        messages={[]}
        status="error"
        error="Something went wrong."
        isSending={false}
        onPrompt={() => {}}
        onRetry={onRetry}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });
});
