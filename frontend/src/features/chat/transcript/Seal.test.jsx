import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Seal from "./Seal";

describe("Seal", () => {
  it("is a button named by its source number", () => {
    render(<Seal number={2} onClick={vi.fn()} />);
    const seal = screen.getByRole("button", { name: "Source 2" });
    expect(seal).toHaveTextContent("2");
    expect(seal).toHaveClass("seal");
    expect(seal).not.toHaveClass("sel");
  });

  it("opens its source when clicked", async () => {
    const onClick = vi.fn();
    render(<Seal number={1} onClick={onClick} />);
    await userEvent.click(screen.getByRole("button", { name: "Source 1" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("reports hover and focus, so its card can be outlined", async () => {
    const onHover = vi.fn();
    render(<Seal number={1} onClick={vi.fn()} onHover={onHover} />);
    const seal = screen.getByRole("button", { name: "Source 1" });
    await userEvent.hover(seal);
    expect(onHover).toHaveBeenLastCalledWith(true);
    await userEvent.unhover(seal);
    expect(onHover).toHaveBeenLastCalledWith(false);
  });

  it("shows when its source is the one selected", () => {
    render(<Seal number={1} selected onClick={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Source 1" })).toHaveClass("sel");
  });

  it("stamps in only when asked", () => {
    const { container, rerender } = render(<Seal number={1} onClick={vi.fn()} />);
    expect(container.querySelector(".stamp")).toBeNull();
    rerender(<Seal number={1} stamp index={2} onClick={vi.fn()} />);
    expect(container.querySelector(".stamp")).toContainElement(screen.getByRole("button", { name: "Source 1" }));
  });
});
