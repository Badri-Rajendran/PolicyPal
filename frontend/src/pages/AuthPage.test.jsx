import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../hooks/useAuth";
import AuthPage from "./AuthPage";

vi.mock("../hooks/useAuth");

describe("AuthPage", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ login: vi.fn(), register: vi.fn() });
  });

  it("starts in sign-in mode", () => {
    render(<AuthPage />);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("says nothing about expiry on an ordinary visit", () => {
    render(<AuthPage />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("explains why the user is back here when the session expired", () => {
    useAuth.mockReturnValue({ status: "expired", login: vi.fn(), register: vi.fn() });
    render(<AuthPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/session has expired/i);
  });

  it("switches to registration and back", async () => {
    render(<AuthPage />);

    await userEvent.click(screen.getByRole("button", { name: "Create one" }));
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
