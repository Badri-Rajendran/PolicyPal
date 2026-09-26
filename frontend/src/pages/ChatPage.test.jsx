import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useMessages } from "../features/chat/useMessages";
import { useThreads } from "../features/chat/useThreads";
import { useAuth } from "../hooks/useAuth";
import * as chatService from "../services/chatService";
import ChatPage from "./ChatPage";

vi.mock("../hooks/useAuth");
vi.mock("../features/chat/useThreads");
vi.mock("../features/chat/useMessages");
vi.mock("../services/chatService");

const threads = [{ id: "t1", title: "Deductibles", updated_at: new Date().toISOString() }];

const question = { id: "q1", role: "user", content: "Compare silver plans", created_at: "2026-09-26T14:00:00Z" };
const answer = {
  id: "a1",
  role: "assistant",
  content: "Here they are.\n\nThe lowest is [Plan: p2].[Source: wiki_Health.txt]",
  created_at: "2026-09-26T14:00:30Z",
  sources: [{ id: "s1", source: "wiki_Health.txt", chunk_id: "c1", relevance: 0.9 }],
  plans: [
    { hios_plan_id: "p1", plan_year: 2026, name: "Bronze 60 HMO", issuer: "Sharp", metal_level: "Bronze", plan_type: "HMO", monthly_premium: "300.00", premium_age: 40, premium_reference: null, deductible: "7000.00", drug_deductible: null, out_of_pocket_max: "9800.00", quality_rating: null, county_name: "San Diego", state: "CA", benefits_url: null, sbc_status: "ok" },
    { hios_plan_id: "p2", plan_year: 2026, name: "Silver 70 HMO", issuer: "Molina", metal_level: "Silver", plan_type: "HMO", monthly_premium: "489.81", premium_age: 40, premium_reference: null, deductible: "5200.00", drug_deductible: null, out_of_pocket_max: "9800.00", quality_rating: null, county_name: "San Diego", state: "CA", benefits_url: null, sbc_status: "ok" },
  ],
};

let threadsState;
let messagesState;

function mockThreads(overrides = {}) {
  threadsState = {
    threads,
    status: "ready",
    error: "",
    createThread: vi.fn().mockResolvedValue({ id: "t2", title: null }),
    removeThread: vi.fn().mockResolvedValue(undefined),
    renameThread: vi.fn().mockResolvedValue({}),
    touchThread: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  };
  useThreads.mockImplementation(() => threadsState);
}

function mockMessages(overrides = {}) {
  messagesState = {
    messages: [],
    status: "ready",
    error: "",
    live: null,
    isSending: false,
    sendError: "",
    stoppedId: null,
    finishedId: null,
    send: vi.fn(),
    stop: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  };
  useMessages.mockImplementation(() => messagesState);
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

const title = () => screen.getByRole("banner");

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn(), token: "tok", expireSession: vi.fn() });
  chatService.getSource.mockReturnValue(new Promise(() => {}));
  mockThreads();
  mockMessages();
});

afterEach(() => {
  localStorage.clear();
});

describe("ChatPage", () => {
  it("renders the sidebar and the chat together, with the main landmark", () => {
    renderAt("/chat/t1");
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(within(title()).getByRole("button", { name: /Rename this thread/ })).toHaveTextContent("Deductibles");
  });

  it("opens no thread at /chat", () => {
    renderAt("/chat");
    expect(title()).toHaveTextContent("New question");
    expect(useMessages).toHaveBeenLastCalledWith(null, expect.any(Function));
  });

  it("treats an unknown thread id as nothing open rather than an error", () => {
    renderAt("/chat/does-not-exist");
    expect(title()).toHaveTextContent("New question");
  });

  it("navigates to a thread when the sidebar selects one", async () => {
    renderAt("/chat");
    await userEvent.click(screen.getByRole("button", { name: "Deductibles" }));
    expect(title()).toHaveTextContent("Deductibles");
    expect(useMessages).toHaveBeenLastCalledWith("t1", expect.any(Function));
  });

  it("keeps the thread list current when an answer finishes", () => {
    renderAt("/chat/t1");
    const onThreadUpdated = useMessages.mock.lastCall[1];
    onThreadUpdated({ id: "t1", title: "Deductibles", updated_at: "2026-09-26T15:00:00Z" });
    expect(threadsState.touchThread).toHaveBeenCalledWith("t1", "Deductibles", "2026-09-26T15:00:00Z");
  });

  it("shows an error with a retry action when threads fail to load", async () => {
    mockThreads({ threads: [], status: "error", error: "Can't reach PolicyPal right now. Check your connection and try again." });
    renderAt("/chat");
    expect(screen.getByRole("alert")).toHaveTextContent("Can't reach PolicyPal");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(threadsState.retry).toHaveBeenCalledOnce();
  });

  it("sends a question directly when a thread is open", async () => {
    renderAt("/chat/t1");
    await userEvent.type(screen.getByRole("textbox", { name: "Your question" }), "What is a deductible?{Enter}");
    expect(messagesState.send).toHaveBeenCalledWith("What is a deductible?");
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveValue("");
  });

  it("creates a thread first when none is open, then sends once it exists", async () => {
    renderAt("/chat");
    await userEvent.type(screen.getByRole("textbox", { name: "Your question" }), "What is a deductible?{Enter}");
    expect(threadsState.createThread).toHaveBeenCalledOnce();
    await waitFor(() => expect(messagesState.send).toHaveBeenCalledWith("What is a deductible?"));
  });

  it("surfaces a send error", () => {
    mockMessages({ sendError: "You're sending requests too quickly. Wait a moment and try again." });
    renderAt("/chat/t1");
    expect(screen.getByRole("alert")).toHaveTextContent("too quickly");
  });

  it("disables the composer while an answer is live, and Stop stops it", async () => {
    mockMessages({ messages: [question], live: { questionId: "q1", stages: [], notices: [], text: "" }, isSending: true });
    renderAt("/chat/t1");
    expect(screen.getByRole("textbox", { name: "Your question" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveAttribute("placeholder", "PolicyPal is answering…");
    await userEvent.click(screen.getByRole("button", { name: "Stop answering" }));
    expect(messagesState.stop).toHaveBeenCalledOnce();
  });

  it("Escape while an answer is live calls stop", async () => {
    mockMessages({ messages: [question], live: { questionId: "q1", stages: [], notices: [], text: "" }, isSending: true });
    renderAt("/chat/t1");
    await userEvent.keyboard("{Escape}");
    expect(messagesState.stop).toHaveBeenCalledOnce();
  });

  it("Ctrl+K starts a new question", async () => {
    renderAt("/chat/t1");
    await userEvent.keyboard("{Control>}k{/Control}");
    expect(threadsState.createThread).toHaveBeenCalledOnce();
    await waitFor(() => expect(useMessages).toHaveBeenLastCalledWith("t2", expect.any(Function)));
  });

  it("/ focuses the composer", async () => {
    renderAt("/chat/t1");
    await userEvent.keyboard("/");
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveFocus();
  });

  it("a starter fills the composer", async () => {
    renderAt("/chat/t1");
    await userEvent.click(screen.getByRole("button", { name: /How is coinsurance different from a copay\?/ }));
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveValue("How is coinsurance different from a copay?");
  });

  it("Ask about this plan fills the composer with its number and name, and focuses it", async () => {
    mockMessages({ messages: [question, answer] });
    renderAt("/chat/t1");
    const row = screen.getByRole("rowheader", { name: /Silver 70 HMO/ });
    await userEvent.click(within(row).getByRole("button", { name: /Ask about this plan/ }));
    const composer = screen.getByRole("textbox", { name: "Your question" });
    expect(composer).toHaveValue("About plan 2, Silver 70 HMO: ");
    expect(composer).toHaveFocus();
  });

  it("the Sources toggle opens the panel on the latest answer with sources, and Esc closes it", async () => {
    mockMessages({ messages: [question, answer, { ...question, id: "q2" }] });
    renderAt("/chat/t1");
    const toggle = screen.getByRole("button", { name: "Sources 1" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(toggle);
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(within(panel).getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Sources 1" })).toHaveAttribute("aria-pressed", "true");

    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument());
  });

  it("a seal opens the panel on its source", async () => {
    mockMessages({ messages: [question, answer] });
    renderAt("/chat/t1");
    await userEvent.click(screen.getAllByRole("button", { name: "Source 1" })[0]);
    const panel = screen.getByRole("complementary", { name: "Sources" });
    expect(within(panel).getByRole("article")).toHaveAttribute("aria-current", "true");
  });

  it("hides the sidebar, remembers it, and shows it again", async () => {
    const { unmount } = renderAt("/chat/t1");
    await userEvent.click(screen.getByRole("button", { name: "Hide the sidebar" }));
    expect(localStorage.getItem("policypal.sidebar")).toBe("hidden");
    expect(screen.queryByRole("complementary", { name: "Your questions" })).not.toBeInTheDocument();
    unmount();

    renderAt("/chat/t1");
    await userEvent.click(screen.getByRole("button", { name: "Show the sidebar" }));
    expect(localStorage.getItem("policypal.sidebar")).toBeNull();
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
  });

  it("renames a thread from the sidebar, and says so when that fails", async () => {
    const user = userEvent.setup();
    const renameThread = vi.fn().mockRejectedValue(new Error("validation failed"));
    mockThreads({ renameThread });
    renderAt("/chat/t1");

    await user.click(screen.getByRole("button", { name: "Options for Deductibles" }));
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    await user.type(screen.getByRole("textbox", { name: "Thread name" }), " 101{Enter}");

    expect(renameThread).toHaveBeenCalledWith("t1", "Deductibles 101");
    expect(await screen.findByRole("status")).toHaveTextContent("Couldn't rename this thread. Try again.");
  });

  it("renames the open thread from its title", async () => {
    const user = userEvent.setup();
    renderAt("/chat/t1");
    await user.click(within(title()).getByRole("button", { name: /Rename this thread/ }));
    await user.type(within(title()).getByRole("textbox", { name: "Thread name" }), "!{Enter}");
    expect(threadsState.renameThread).toHaveBeenCalledWith("t1", "Deductibles!");
  });

  it("deletes the open thread and goes back to /chat", async () => {
    const user = userEvent.setup();
    renderAt("/chat/t1");
    await user.click(screen.getByRole("button", { name: "Options for Deductibles" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(threadsState.removeThread).toHaveBeenCalledWith("t1");
    await waitFor(() => expect(useMessages).toHaveBeenLastCalledWith(null, expect.any(Function)));
  });

  it("asks an account without a profile to add one, and nobody else", () => {
    useAuth.mockReturnValue({ user: { email: "alice@example.com", profile_complete: false }, logout: vi.fn() });
    const { unmount } = renderAt("/chat");
    expect(screen.getByRole("link", { name: "your profile" })).toHaveAttribute("href", "/profile");
    unmount();

    useAuth.mockReturnValue({ user: { email: "alice@example.com", profile_complete: true }, logout: vi.fn() });
    renderAt("/chat");
    expect(screen.queryByText(/add your ZIP code/)).not.toBeInTheDocument();
  });
});
