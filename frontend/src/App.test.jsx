import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { useAuth } from "./hooks/useAuth";

vi.mock("./hooks/useAuth");
vi.mock("./pages/AuthPage", () => ({ default: () => <div>auth-page</div> }));
vi.mock("./pages/ChatPage", () => ({ default: () => <div>chat-page</div> }));

describe("App", () => {
  it("shows the auth page when signed out", () => {
    useAuth.mockReturnValue({ status: "signed-out" });
    render(<App />);
    expect(screen.getByText("auth-page")).toBeInTheDocument();
  });

  it("shows the chat page when signed in", () => {
    useAuth.mockReturnValue({ status: "signed-in" });
    render(<App />);
    expect(screen.getByText("chat-page")).toBeInTheDocument();
  });
});
