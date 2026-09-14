import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { useAuth } from "./hooks/useAuth";

vi.mock("./hooks/useAuth");
vi.mock("./pages/AuthPage", () => ({ default: ({ mode }) => <div>auth-page:{mode}</div> }));
vi.mock("./pages/ChatPage", () => ({ default: () => <div>chat-page</div> }));

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("App routing", () => {
  it("sends a signed-out visitor to sign in", () => {
    useAuth.mockReturnValue({ status: "signed-out" });
    renderAt("/chat");
    expect(screen.getByText("auth-page:login")).toBeInTheDocument();
  });

  it("keeps a signed-out visitor out of a linked thread", () => {
    useAuth.mockReturnValue({ status: "signed-out" });
    renderAt("/chat/t1");
    expect(screen.getByText("auth-page:login")).toBeInTheDocument();
  });

  it("opens registration on its own route", () => {
    useAuth.mockReturnValue({ status: "signed-out" });
    renderAt("/register");
    expect(screen.getByText("auth-page:register")).toBeInTheDocument();
  });

  it("shows the chat page when signed in", () => {
    useAuth.mockReturnValue({ status: "signed-in" });
    renderAt("/chat");
    expect(screen.getByText("chat-page")).toBeInTheDocument();
  });

  it("opens a linked thread directly", () => {
    useAuth.mockReturnValue({ status: "signed-in" });
    renderAt("/chat/t1");
    expect(screen.getByText("chat-page")).toBeInTheDocument();
  });

  it("sends a signed-in visitor away from the auth routes", () => {
    useAuth.mockReturnValue({ status: "signed-in" });
    renderAt("/login");
    expect(screen.getByText("chat-page")).toBeInTheDocument();
  });

  it("falls back to the chat route for anything unknown", () => {
    useAuth.mockReturnValue({ status: "signed-in" });
    renderAt("/nowhere");
    expect(screen.getByText("chat-page")).toBeInTheDocument();
  });
});
