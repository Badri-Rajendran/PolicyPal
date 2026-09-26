import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EmptyState from "./EmptyState";

describe("EmptyState", () => {
  it("asks what the user would like to know, and says where answers come from", () => {
    render(<EmptyState onPrompt={() => {}} />);
    expect(screen.getByRole("heading", { level: 1, name: "What would you like to know about your coverage?" })).toBeInTheDocument();
    expect(screen.getByText(/Every claim links to the passage it came from\./)).toBeInTheDocument();
  });

  it("offers four starters, the two plan ones labelled Plans near you", () => {
    render(<EmptyState onPrompt={() => {}} />);
    const starters = screen.getAllByRole("button");
    expect(starters).toHaveLength(4);
    expect(screen.getAllByText("Plans near you")).toHaveLength(2);
    expect(screen.getByText("A term")).toBeInTheDocument();
    expect(screen.getByText("A rule")).toBeInTheDocument();
  });

  it("fills the composer with a starter's question", async () => {
    const onPrompt = vi.fn();
    render(<EmptyState onPrompt={onPrompt} />);
    await userEvent.click(screen.getByRole("button", { name: /How is coinsurance different from a copay\?/ }));
    expect(onPrompt).toHaveBeenCalledWith("How is coinsurance different from a copay?");
  });
});
