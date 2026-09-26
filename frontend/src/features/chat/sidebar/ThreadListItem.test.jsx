import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ThreadListItem from "./ThreadListItem";

const thread = { id: "t1", title: "Deductibles in health insurance" };

function renderItem(props = {}) {
  const handlers = { onSelect: vi.fn(), onRename: vi.fn(), onDelete: vi.fn() };
  render(
    <ul>
      <ThreadListItem thread={thread} active={false} query="" {...handlers} {...props} />
    </ul>,
  );
  return handlers;
}

async function choose(user, item) {
  await user.click(screen.getByRole("button", { name: `Options for ${thread.title}` }));
  await user.click(screen.getByRole("menuitem", { name: item }));
}

describe("ThreadListItem", () => {
  it("shows the thread title", () => {
    renderItem();
    expect(screen.getByRole("button", { name: thread.title })).toBeInTheDocument();
  });

  it("falls back to a placeholder title", () => {
    renderItem({ thread: { id: "t2", title: null } });
    expect(screen.getByRole("button", { name: "New question" })).toBeInTheDocument();
  });

  it("calls onSelect with the thread id", async () => {
    const { onSelect } = renderItem();
    await userEvent.click(screen.getByRole("button", { name: thread.title }));
    expect(onSelect).toHaveBeenCalledWith("t1");
  });

  it("marks the active thread as the current page", () => {
    renderItem({ active: true });
    expect(screen.getByRole("button", { name: thread.title })).toHaveAttribute("aria-current", "page");
  });

  it("wraps each match of the search in a mark", () => {
    const { container } = render(
      <ul>
        <ThreadListItem thread={{ id: "t3", title: "MRI cost, and an mri" }} active={false} query="mri" onSelect={vi.fn()} onRename={vi.fn()} onDelete={vi.fn()} />
      </ul>,
    );
    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["MRI", "mri"]);
  });

  it("renames inline: Enter saves the trimmed name", async () => {
    const user = userEvent.setup();
    const { onRename, onSelect } = renderItem();
    await choose(user, "Rename");
    const input = screen.getByRole("textbox", { name: "Thread name" });
    expect(input).toHaveValue(thread.title);
    expect(input).toHaveFocus();
    expect(screen.getByText("Enter to save, Esc to cancel")).toBeInTheDocument();
    await user.clear(input);
    await user.type(input, "  New  {Enter}");
    expect(onRename).toHaveBeenCalledWith("t1", "New");
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("Esc cancels a rename without saving", async () => {
    const user = userEvent.setup();
    const { onRename } = renderItem();
    await choose(user, "Rename");
    await user.type(screen.getByRole("textbox", { name: "Thread name" }), " more{Escape}");
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: thread.title })).toHaveFocus();
  });

  it("refuses a blank name", async () => {
    const user = userEvent.setup();
    const { onRename } = renderItem();
    await choose(user, "Rename");
    const input = screen.getByRole("textbox", { name: "Thread name" });
    await user.clear(input);
    await user.keyboard("{Enter}");
    expect(onRename).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter a name");
  });

  it("an unchanged name just closes the editor", async () => {
    const user = userEvent.setup();
    const { onRename } = renderItem();
    await choose(user, "Rename");
    await user.keyboard("{Enter}");
    expect(onRename).not.toHaveBeenCalled();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("asks before deleting, and Keep it cancels", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderItem();
    await choose(user, "Delete");
    const question = screen.getByText(/and its answers\?/);
    expect(question).toHaveTextContent(`Delete ${thread.title} and its answers?`);
    expect(question.querySelector("strong")).toHaveTextContent(thread.title);
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: thread.title })).toHaveFocus();
  });

  it("deletes once confirmed, all from the keyboard", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderItem();
    await user.click(screen.getByRole("button", { name: `Options for ${thread.title}` }));
    await user.keyboard("{ArrowDown}{Enter}");
    expect(screen.getByRole("button", { name: "Keep it" })).toHaveFocus();
    await user.keyboard("{Shift>}{Tab}{/Shift}{Enter}");
    expect(onDelete).toHaveBeenCalledWith("t1");
  });

  it("Esc cancels a delete", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderItem();
    await choose(user, "Delete");
    await user.keyboard("{Escape}");
    expect(onDelete).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Keep it" })).not.toBeInTheDocument();
  });
});
