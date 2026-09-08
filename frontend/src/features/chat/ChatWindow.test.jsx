import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatWindow from "./ChatWindow";
import { useMessages } from "./useMessages";

vi.mock("./useMessages");

function mockMessagesState(overrides = {}) {
  const send = vi.fn();
  useMessages.mockReturnValue({
    messages: [],
    status: "ready",
    isSending: false,
    sendError: "",
    send,
    ...overrides,
  });
  return send;
}

describe("ChatWindow", () => {
  beforeEach(() => {
    mockMessagesState();
  });

  it("shows the thread title, falling back to 'New question'", () => {
    render(<ChatWindow threadId="t1" threadTitle={null} onCreateThread={() => {}} onThreadTitled={() => {}} />);
    expect(screen.getByRole("heading", { name: "New question" })).toBeInTheDocument();
  });

  it("sends a message directly when a thread already exists", async () => {
    const send = mockMessagesState();
    render(<ChatWindow threadId="t1" threadTitle="Deductibles" onCreateThread={() => {}} onThreadTitled={() => {}} />);

    await userEvent.type(screen.getByLabelText("Ask about your policy"), "What is a deductible?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(send).toHaveBeenCalledWith("What is a deductible?");
  });

  it("creates a thread first when none is selected, then sends once it exists", async () => {
    const send = mockMessagesState();
    const onCreateThread = vi.fn().mockResolvedValue({ id: "t2" });
    const { rerender } = render(
      <ChatWindow threadId={null} threadTitle={null} onCreateThread={onCreateThread} onThreadTitled={() => {}} />,
    );

    await userEvent.type(screen.getByLabelText("Ask about your policy"), "What is a deductible?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(onCreateThread).toHaveBeenCalledOnce();
    expect(send).not.toHaveBeenCalled();

    rerender(<ChatWindow threadId="t2" threadTitle={null} onCreateThread={onCreateThread} onThreadTitled={() => {}} />);

    expect(send).toHaveBeenCalledWith("What is a deductible?");
  });

  it("surfaces a send error", () => {
    mockMessagesState({ sendError: "You're sending requests too quickly. Wait a moment and try again." });
    render(<ChatWindow threadId="t1" threadTitle="Deductibles" onCreateThread={() => {}} onThreadTitled={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("too quickly");
  });
});
