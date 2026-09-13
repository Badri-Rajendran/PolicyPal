import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("invites the user to ask a question", () => {
    render(<EmptyState onPrompt={() => {}} />);
    expect(screen.getByRole("heading", { name: "Ask about your policy" })).toBeInTheDocument();
  });

  it("fills the composer when a suggested prompt is clicked", async () => {
    const onPrompt = vi.fn();
    render(<EmptyState onPrompt={onPrompt} />);
    const [firstPrompt] = screen.getAllByRole("button");
    await userEvent.click(firstPrompt);
    expect(onPrompt).toHaveBeenCalledWith(firstPrompt.textContent);
  });
});
