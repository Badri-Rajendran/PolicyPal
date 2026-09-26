import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import Composer from "./Composer";

function renderComposer(props = {}) {
  const handlers = { onChange: vi.fn(), onSubmit: vi.fn(), onStop: vi.fn() };
  render(<Composer value="What is a deductible?" isSending={false} placeholder="Ask a follow-up" {...handlers} {...props} />);
  return handlers;
}

function Controlled({ onSubmit }) {
  const [value, setValue] = useState("");
  return <Composer value={value} onChange={setValue} onSubmit={onSubmit} onStop={vi.fn()} isSending={false} />;
}

describe("Composer", () => {
  it("is a labelled form with a labelled question box and its placeholder", () => {
    renderComposer();
    expect(screen.getByRole("form", { name: "Ask a question" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your question" })).toHaveAttribute("placeholder", "Ask a follow-up");
  });

  it("submits the trimmed text on Enter", async () => {
    const onSubmit = vi.fn();
    render(<Controlled onSubmit={onSubmit} />);
    await userEvent.type(screen.getByRole("textbox"), "  What is a deductible?  {Enter}");
    expect(onSubmit).toHaveBeenCalledWith("What is a deductible?");
  });

  it("does not submit on Shift+Enter", async () => {
    const { onSubmit } = renderComposer();
    await userEvent.type(screen.getByRole("textbox"), "{Shift>}{Enter}{/Shift}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits from the Send button", async () => {
    const { onSubmit } = renderComposer();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSubmit).toHaveBeenCalledWith("What is a deductible?");
  });

  it("never submits empty or whitespace-only content", async () => {
    const { onSubmit } = renderComposer({ value: "   " });
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "{Enter}");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("while an answer streams, disables the box and offers Stop", async () => {
    const { onStop, onSubmit } = renderComposer({ isSending: true });
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(screen.getByText("Press Esc or Stop to cancel this answer")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Stop answering" }));
    expect(onStop).toHaveBeenCalledOnce();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("shows the hint for sending", () => {
    renderComposer();
    expect(screen.getByText("Enter to send, Shift+Enter for a new line")).toBeInTheDocument();
  });

  it("discloses that questions are sent to OpenAI", () => {
    renderComposer();
    expect(
      screen.getByText(
        "Questions and the passages found for them are sent to OpenAI to write answers. Don't include personal details.",
      ),
    ).toBeInTheDocument();
  });

  it("can be focused through its ref", () => {
    const ref = createRef();
    render(<Composer ref={ref} value="" onChange={vi.fn()} onSubmit={vi.fn()} onStop={vi.fn()} isSending={false} />);
    ref.current.focus();
    expect(screen.getByRole("textbox")).toHaveFocus();
  });

  it("reports typing", async () => {
    const { onChange } = renderComposer({ value: "" });
    await userEvent.type(screen.getByRole("textbox"), "a");
    expect(onChange).toHaveBeenCalledWith("a");
  });
});
