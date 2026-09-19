import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import { ApiError } from "../../services/apiClient";
import { lookupCounties } from "../../services/profileService";
import { todayIso } from "../../utils/age";
import AuthForm from "./AuthForm";

vi.mock("../../hooks/useAuth");
vi.mock("../../services/profileService");

const alpha = { county_fips: "48001", county_name: "Anderson", state: "TX" };
const beta = { county_fips: "48213", county_name: "Henderson", state: "TX" };

function yearsAgoPlus(years, days) {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  date.setDate(date.getDate() + days);
  return todayIso(date);
}

async function fillSignup({ zip = "75801", dateOfBirth = "1990-05-17" } = {}) {
  await userEvent.type(screen.getByLabelText("Email"), "alice@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct-horse-1");
  await userEvent.type(screen.getByLabelText("ZIP code"), zip);
  // A date input takes its value whole; typing it digit by digit is not how browsers fill it.
  fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: dateOfBirth } });
}

describe("AuthForm", () => {
  const login = vi.fn();
  const register = vi.fn();

  beforeEach(() => {
    login.mockReset().mockResolvedValue(undefined);
    register.mockReset().mockResolvedValue(undefined);
    useAuth.mockReturnValue({ login, register });
    lookupCounties.mockReset().mockResolvedValue({ counties: [alpha], marketplace_state: true });
  });

  it("refuses anyone a day short of 13 without sending anything", async () => {
    render(<AuthForm mode="register" onModeChange={() => {}} />);

    await fillSignup({ dateOfBirth: yearsAgoPlus(13, 1) });
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(screen.getByText("You must be at least 13 to use PolicyPal.")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it("creates an account with the profile once everything checks out", async () => {
    render(<AuthForm mode="register" onModeChange={() => {}} />);

    await fillSignup({ dateOfBirth: yearsAgoPlus(13, 0) });
    await screen.findByText("Anderson County, TX");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(register).toHaveBeenCalledWith("alice@example.com", "correct-horse-1", {
      zip_code: "75801",
      date_of_birth: yearsAgoPlus(13, 0),
      county_fips: "48001",
    });
  });

  it("asks which county when the ZIP code spans several", async () => {
    lookupCounties.mockResolvedValue({ counties: [alpha, beta], marketplace_state: true });
    render(<AuthForm mode="register" onModeChange={() => {}} />);

    await fillSignup({ zip: "75751" });
    await screen.findByLabelText("County");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByText("Choose your county.")).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();

    await userEvent.selectOptions(screen.getByLabelText("County"), "48213");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(register).toHaveBeenCalledWith("alice@example.com", "correct-horse-1", expect.objectContaining({ county_fips: "48213" }));
  });

  it("shows the server's verdict on a field beside that field", async () => {
    register.mockRejectedValue(
      new ApiError("validation failed", 422, [{ field: "date_of_birth", message: "You must be at least 13 to use PolicyPal." }]),
    );
    render(<AuthForm mode="register" onModeChange={() => {}} />);

    await fillSignup();
    await screen.findByText("Anderson County, TX");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText("You must be at least 13 to use PolicyPal.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("asks for no profile to sign in", () => {
    render(<AuthForm mode="login" onModeChange={() => {}} />);

    expect(screen.queryByLabelText("ZIP code")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Date of birth")).not.toBeInTheDocument();
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
