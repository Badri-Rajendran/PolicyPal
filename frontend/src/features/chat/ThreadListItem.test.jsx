import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ThreadListItem from "./ThreadListItem";

const thread = { id: "t1", title: "Deductibles in health insurance" };

describe("ThreadListItem", () => {
  it("shows the thread title", () => {
    render(<ThreadListItem thread={thread} active={false} onSelect={() => {}} onDelete={() => {}} />);
    expect(screen.getByRole("button", { name: thread.title })).toBeInTheDocument();
  });

  it("falls back to a placeholder title", () => {
    render(<ThreadListItem thread={{ id: "t2", title: null }} active={false} onSelect={() => {}} onDelete={() => {}} />);
    expect(screen.getByRole("button", { name: "New question" })).toBeInTheDocument();
  });

  it("calls onSelect with the thread id", async () => {
    const onSelect = vi.fn();
    render(<ThreadListItem thread={thread} active={false} onSelect={onSelect} onDelete={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: thread.title }));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });

  it("calls onDelete without triggering onSelect", async () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(<ThreadListItem thread={thread} active={false} onSelect={onSelect} onDelete={onDelete} />);
    await userEvent.click(screen.getByRole("button", { name: `Delete "${thread.title}"` }));
    expect(onDelete).toHaveBeenCalledWith("t1");
    expect(onSelect).not.toHaveBeenCalled();
  });
});
