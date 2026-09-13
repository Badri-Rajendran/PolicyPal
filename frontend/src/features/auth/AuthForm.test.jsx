import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import AuthForm from "./AuthForm";

vi.mock("../../hooks/useAuth");

describe("AuthForm", () => {
  const login = vi.fn();
  const register = vi.fn();

  beforeEach(() => {
    login.mockReset().mockResolvedValue(undefined);
    register.mockReset().mockResolvedValue(undefined);
    useAuth.mockReturnValue({ login, register });
  });

  it("signs in with a valid email and password", async () => {
    render(<AuthForm mode="login" onModeChange={() => {}} />);

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(login).toHaveBeenCalledWith("alice@example.com", "correct-horse-1");
  });

  it("rejects an invalid email without calling the API", async () => {
    render(<AuthForm mode="login" onModeChange={() => {}} />);

    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-1");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("requires at least 8 characters to register", async () => {
    render(<AuthForm mode="register" onModeChange={() => {}} />);

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText("Use at least 8 characters.")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("shows the server error when sign in fails", async () => {
    login.mockRejectedValue(new Error("invalid email or password"));
    render(<AuthForm mode="login" onModeChange={() => {}} />);

    await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("invalid email or password");
  });

  it("lets the user switch modes", async () => {
    const onModeChange = vi.fn();
    render(<AuthForm mode="login" onModeChange={onModeChange} />);

    await userEvent.click(screen.getByRole("button", { name: "Create one" }));

    expect(onModeChange).toHaveBeenCalledWith("register");
  });
});
