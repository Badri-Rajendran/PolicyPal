import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
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

function mockThreads(overrides = {}) {
  useThreads.mockReturnValue({
    threads,
    status: "ready",
    error: "",
    createThread: vi.fn(),
    removeThread: vi.fn(),
    touchThread: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  });
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:threadId" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn() });
  });

  it("renders the sidebar and chat window together", () => {
    mockThreads();
    renderAt("/chat/t1");

    expect(screen.getByRole("button", { name: "Deductibles" })).toBeInTheDocument();
    expect(screen.getByTestId("chat-window")).toHaveTextContent("Deductibles");
  });

  it("opens the thread named in the URL", () => {
    mockThreads();
    renderAt("/chat/t1");
    expect(screen.getByTestId("chat-window")).toHaveTextContent("Deductibles");
  });

  it("opens no thread at /chat", () => {
    mockThreads();
    renderAt("/chat");
    expect(screen.getByTestId("chat-window")).toHaveTextContent("New question");
  });

  it("treats an unknown thread id as nothing open rather than an error", () => {
    mockThreads();
    renderAt("/chat/does-not-exist");
    expect(screen.getByTestId("chat-window")).toHaveTextContent("New question");
  });

  it("navigates to a thread when the sidebar selects one", async () => {
    mockThreads();
    renderAt("/chat");

    await userEvent.click(screen.getByRole("button", { name: "Deductibles" }));

    expect(screen.getByTestId("chat-window")).toHaveTextContent("Deductibles");
  });

  it("shows an error with a retry action when threads fail to load", async () => {
    const retry = vi.fn();
    mockThreads({
      threads: [],
      status: "error",
      error: "Can't reach PolicyPal right now. Check your connection and try again.",
      retry,
    });

    renderAt("/chat");

    expect(screen.getByRole("alert")).toHaveTextContent("Can't reach PolicyPal");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
