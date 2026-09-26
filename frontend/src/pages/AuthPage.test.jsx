import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../hooks/useAuth";
import AuthPage from "./AuthPage";

vi.mock("../hooks/useAuth");

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthPage", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ login: vi.fn(), register: vi.fn() });
  });

  it("signs in on the login route", () => {
    renderAt("/login");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("exposes the card as the main landmark", () => {
    renderAt("/login");
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("registers on the register route", () => {
    renderAt("/register");
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();
  });

  it("says nothing about expiry on an ordinary visit", () => {
    renderAt("/login");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("explains why the user is back here when the session expired", () => {
    useAuth.mockReturnValue({ status: "expired", login: vi.fn(), register: vi.fn() });
    renderAt("/login");
    expect(screen.getByRole("status")).toHaveTextContent(/session has expired/i);
  });

  it("leads with the promise and an example cited answer", () => {
    renderAt("/login");
    expect(
      screen.getByRole("heading", { level: 1, name: "Answers about your health coverage, with the source for every claim." }),
    ).toBeInTheDocument();
    expect(screen.getByText("A fixed amount you pay for a plan-covered service, like $30.")).toBeInTheDocument();
    expect(screen.getByText("A percentage of the cost that you pay for each plan-covered service, like 20%.")).toBeInTheDocument();
  });

  it("heads the sign-in form, and the register form, in sentence case", () => {
    const { unmount } = renderAt("/login");
    expect(screen.getByRole("heading", { level: 2, name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Pick up your questions where you left them.")).toBeInTheDocument();
    unmount();

    renderAt("/register");
    expect(screen.getByRole("heading", { level: 2, name: "Create an account" })).toBeInTheDocument();
    expect(screen.getByLabelText("ZIP code")).toBeInTheDocument();
    expect(screen.getByLabelText("Date of birth")).toBeInTheDocument();
  });

  it("lets the password be shown", async () => {
    renderAt("/login");
    const password = screen.getByLabelText("Password");
    await userEvent.type(password, "correct horse");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Hide password" })).toHaveAttribute("aria-pressed", "true");
  });

  it("navigates between the two modes", async () => {
    renderAt("/login");

    await userEvent.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("button", { name: "Create account" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });
});
