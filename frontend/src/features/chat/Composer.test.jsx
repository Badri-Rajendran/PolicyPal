import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Composer from "./Composer";

describe("Composer", () => {
  it("submits on Enter", async () => {
    const onSubmit = vi.fn();
    render(<Composer value="What is a deductible?" onChange={() => {}} onSubmit={onSubmit} disabled={false} />);
    await userEvent.type(screen.getByLabelText("Ask about your policy"), "{Enter}");
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("does not submit on Shift+Enter", async () => {
    const onSubmit = vi.fn();
    render(<Composer value="What is a deductible?" onChange={() => {}} onSubmit={onSubmit} disabled={false} />);
    await userEvent.type(screen.getByLabelText("Ask about your policy"), "{Shift>}{Enter}{/Shift}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("does not submit empty or whitespace-only content", async () => {
    const onSubmit = vi.fn();
    render(<Composer value="   " onChange={() => {}} onSubmit={onSubmit} disabled={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables the textarea and button while sending", () => {
    render(<Composer value="" onChange={() => {}} onSubmit={() => {}} disabled />);
    expect(screen.getByLabelText("Ask about your policy")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});
