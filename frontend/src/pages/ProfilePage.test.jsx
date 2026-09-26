import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useThreads } from "../features/chat/useThreads";
import { useProfile } from "../features/profile/useProfile";
import { useAuth } from "../hooks/useAuth";
import ProfilePage from "./ProfilePage";

vi.mock("../hooks/useAuth");
vi.mock("../features/chat/useThreads");
vi.mock("../features/profile/useProfile");
vi.mock("../features/profile/ProfileForm", () => ({
  default: ({ profile }) => <div data-testid="profile-form">{profile.zip_code}</div>,
}));

let threadsState;

function renderPage(state) {
  useProfile.mockReturnValue({ profile: null, counties: undefined, error: "", retry: vi.fn(), save: vi.fn(), ...state });
  render(
    <MemoryRouter initialEntries={["/profile"]}>
      <Routes>
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/chat" element={<div>chat-page</div>} />
        <Route path="/chat/:threadId" element={<div>chat-thread</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  localStorage.clear();
  useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn() });
  threadsState = {
    threads: [{ id: "t1", title: "Deductibles", updated_at: new Date().toISOString() }],
    status: "ready",
    error: "",
    createThread: vi.fn(),
    removeThread: vi.fn().mockResolvedValue(undefined),
    renameThread: vi.fn().mockResolvedValue({}),
    touchThread: vi.fn(),
    retry: vi.fn(),
  };
  useThreads.mockImplementation(() => threadsState);
});

describe("ProfilePage", () => {
  it("says it is loading", () => {
    renderPage({ status: "loading" });
    expect(screen.getByText("Loading your profile…")).toHaveAttribute("role", "status");
  });

  it("offers a retry when loading fails", async () => {
    const retry = vi.fn();
    renderPage({ status: "error", error: "Something went wrong.", retry });

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
  });

  it("shows the form, a way back, and what happens to the data", () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });

    expect(screen.getByRole("heading", { level: 1, name: "Your profile" })).toBeInTheDocument();
    expect(screen.getByTestId("profile-form")).toHaveTextContent("75801");
    expect(screen.getByRole("link", { name: /Back to your questions/ })).toHaveAttribute("href", "/chat");
    expect(screen.getByText(/never sent to the AI model/)).toBeInTheDocument();
  });

  it("explains where the data goes, in an aside", () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });
    const aside = screen.getByRole("complementary", { name: "How this is used" });
    expect(within(aside).getByRole("heading", { name: "Where this goes" })).toBeInTheDocument();
    expect(aside).toHaveTextContent("Anything you type in a question is sent, so keep personal details out of questions.");
  });

  it("sits in the app shell: the sidebar's New question goes to the chat", async () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New question" }));
    expect(screen.getByText("chat-page")).toBeInTheDocument();
    expect(threadsState.createThread).not.toHaveBeenCalled();
  });

  it("opens a thread from the sidebar", async () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });
    await userEvent.click(screen.getByRole("button", { name: "Deductibles" }));
    expect(screen.getByText("chat-thread")).toBeInTheDocument();
  });

  it("hides and shows the sidebar", async () => {
    renderPage({ status: "ready", profile: { zip_code: "75801" } });
    await userEvent.click(screen.getByRole("button", { name: "Hide the sidebar" }));
    expect(screen.queryByRole("complementary", { name: "Your questions" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Show the sidebar" }));
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
  });
});
