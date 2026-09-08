import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../hooks/useAuth";
import { useThreads } from "../features/chat/useThreads";
import ChatPage from "./ChatPage";

vi.mock("../hooks/useAuth");
vi.mock("../features/chat/useThreads");
vi.mock("../features/chat/ChatWindow", () => ({
  default: ({ threadTitle }) => <div data-testid="chat-window">{threadTitle || "New question"}</div>,
}));

const threads = [{ id: "t1", title: "Deductibles" }];

describe("ChatPage", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn() });
  });

  it("renders the sidebar and chat window together", () => {
    useThreads.mockReturnValue({
      threads,
      status: "ready",
      error: "",
      selectedThreadId: "t1",
      selectThread: vi.fn(),
      createThread: vi.fn(),
      removeThread: vi.fn(),
      touchThread: vi.fn(),
      retry: vi.fn(),
    });

    render(<ChatPage />);

    expect(screen.getByRole("button", { name: "Deductibles" })).toBeInTheDocument();
    expect(screen.getByTestId("chat-window")).toHaveTextContent("Deductibles");
  });

  it("shows an error with a retry action when threads fail to load", async () => {
    const retry = vi.fn();
    useThreads.mockReturnValue({
      threads: [],
      status: "error",
      error: "Can't reach PolicyPal right now. Check your connection and try again.",
      selectedThreadId: null,
      selectThread: vi.fn(),
      createThread: vi.fn(),
      removeThread: vi.fn(),
      touchThread: vi.fn(),
      retry,
    });

    render(<ChatPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("Can't reach PolicyPal");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
