import { render, screen } from "@testing-library/react";
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
});
