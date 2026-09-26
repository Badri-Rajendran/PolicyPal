import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import TextField from "./TextField";

describe("TextField", () => {
  it("associates the label with the input", () => {
    render(<TextField id="email" label="Email" value="" onChange={() => {}} />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  it("shows no error message by default", () => {
    render(<TextField id="email" label="Email" value="" onChange={() => {}} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "false");
  });

  it("shows and associates an error message", () => {
    render(<TextField id="email" label="Email" value="" onChange={() => {}} error="Enter a valid email address." />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Enter a valid email address.")).toHaveAttribute("id", "email-error");
    expect(input).toHaveAttribute("aria-describedby", "email-error");
  });

  it("shows and associates a hint", () => {
    render(<TextField id="dob" label="Date of birth" value="" onChange={() => {}} hint="Never shown to the AI model." />);
    expect(screen.getByLabelText("Date of birth")).toHaveAccessibleDescription("Never shown to the AI model.");
  });

  it("lets an error take the hint's place", () => {
    render(<TextField id="dob" label="Date of birth" value="" onChange={() => {}} hint="Never shown." error="Enter your date of birth." />);
    expect(screen.queryByText("Never shown.")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Date of birth")).toHaveAccessibleDescription("Enter your date of birth.");
  });

  it("has no show/hide button for an ordinary field", () => {
    render(<TextField id="email" label="Email" value="" onChange={() => {}} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("lets a password be shown and hidden", async () => {
    const user = userEvent.setup();
    render(<TextField id="pw" label="Password" type="password" value="secret" onChange={() => {}} />);
    const input = screen.getByLabelText("Password");
    expect(input).toHaveAttribute("type", "password");
    const toggle = screen.getByRole("button", { name: "Show password" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(input).toHaveAttribute("type", "text");
    const hide = screen.getByRole("button", { name: "Hide password" });
    expect(hide).toHaveAttribute("aria-pressed", "true");
    await user.click(hide);
    expect(input).toHaveAttribute("type", "password");
  });
});
