import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import JumpToLatest from "./JumpToLatest";

describe("JumpToLatest", () => {
  it("is a button that jumps to the latest answer", async () => {
    const onClick = vi.fn();
    render(<JumpToLatest onClick={onClick} />);
    const button = screen.getByRole("button", { name: "Jump to latest" });
    expect(button).toHaveClass("jump");
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });
});
