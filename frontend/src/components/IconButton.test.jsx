import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { X } from "lucide-react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import IconButton from "./IconButton";

describe("IconButton", () => {
  it("is a button named by its label, with the icon hidden from screen readers", () => {
    const { container } = render(
      <IconButton label="Close sources">
        <X className="i" aria-hidden="true" />
      </IconButton>,
    );
    const button = screen.getByRole("button", { name: "Close sources" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toHaveClass("iconbtn");
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("calls onClick, passes other props through and forwards its ref", async () => {
    const onClick = vi.fn();
    const ref = createRef();
    render(
      <IconButton label="Hide the sidebar" onClick={onClick} aria-expanded="false" className="extra" ref={ref}>
        <X />
      </IconButton>,
    );
    const button = screen.getByRole("button", { name: "Hide the sidebar" });
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveClass("iconbtn", "extra");
    expect(ref.current).toBe(button);
  });

  it("can be disabled", () => {
    render(
      <IconButton label="Send" disabled>
        <X />
      </IconButton>,
    );
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
