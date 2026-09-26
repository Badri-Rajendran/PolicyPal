import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Button from "./Button";

describe("Button", () => {
  it("renders its children as a primary button by default", () => {
    render(<Button>Send</Button>);
    const button = screen.getByRole("button", { name: "Send" });
    expect(button).toHaveClass("btn");
    expect(button).not.toHaveClass("ghost");
  });

  it("applies the ghost and danger variants", () => {
    render(
      <>
        <Button variant="ghost">Keep it</Button>
        <Button variant="danger">Delete</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Keep it" })).toHaveClass("btn", "ghost");
    expect(screen.getByRole("button", { name: "Delete" })).toHaveClass("btn", "danger");
  });

  it("keeps an extra class name", () => {
    render(<Button className="sm">Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("btn", "sm");
  });

  it("calls onClick when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Send</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("shows a spinner, says Working… to screen readers, and disables itself while busy", () => {
    const { container } = render(<Button busy>Send</Button>);
    const button = screen.getByRole("button", { name: "Working…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(container.querySelector(".spinner")).toHaveAttribute("aria-hidden", "true");
  });

  it("respects an explicit disabled prop", () => {
    render(<Button disabled>Send</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
