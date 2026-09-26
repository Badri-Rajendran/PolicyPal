import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ChatHeader from "./ChatHeader";

function renderHeader(props = {}) {
  const handlers = { onRename: vi.fn(), onToggleSources: vi.fn(), onShowSidebar: vi.fn(), onOpenDrawer: vi.fn(), onNewQuestion: vi.fn() };
  render(
    <ChatHeader title="Compare silver plans near me" sourcesCount={2} sourcesOpen={false} sidebarHidden={false} {...handlers} {...props} />,
  );
  return handlers;
}

describe("ChatHeader", () => {
  it("is the page's banner, with the thread's title", () => {
    renderHeader();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Rename this thread/ })).toHaveTextContent("Compare silver plans near me");
  });

  it("renames inline: Enter saves the trimmed title", async () => {
    const user = userEvent.setup();
    const { onRename } = renderHeader();
    await user.click(screen.getByRole("button", { name: /Rename this thread/ }));
    const input = screen.getByRole("textbox", { name: "Thread name" });
    expect(input).toHaveValue("Compare silver plans near me");
    expect(input).toHaveFocus();
    await user.clear(input);
    await user.type(input, "  Silver plans, San Diego {Enter}");
    expect(onRename).toHaveBeenCalledWith("Silver plans, San Diego");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("Esc cancels, and a blank or unchanged title saves nothing", async () => {
    const user = userEvent.setup();
    const { onRename } = renderHeader();
    await user.click(screen.getByRole("button", { name: /Rename this thread/ }));
    await user.type(screen.getByRole("textbox"), " more{Escape}");
    expect(screen.getByRole("button", { name: /Rename this thread/ })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: /Rename this thread/ }));
    await user.clear(screen.getByRole("textbox"));
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
    await user.type(screen.getByRole("textbox"), "Compare silver plans near me{Enter}");
    expect(onRename).not.toHaveBeenCalled();
  });

  it("shows a plain title when the thread can't be renamed", () => {
    renderHeader({ title: "New question", onRename: undefined });
    expect(screen.queryByRole("button", { name: /Rename this thread/ })).not.toBeInTheDocument();
    expect(screen.getByText("New question")).toBeInTheDocument();
  });

  it("toggles the Sources panel, showing the count and whether it's open", async () => {
    const { onToggleSources } = renderHeader({ sourcesOpen: true });
    const toggle = screen.getByRole("button", { name: "Sources 2" });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(toggle).toHaveClass("pill-btn", "on");
    await userEvent.click(toggle);
    expect(onToggleSources).toHaveBeenCalledOnce();
  });

  it("disables Sources when there are none", () => {
    renderHeader({ sourcesCount: 0 });
    expect(screen.getByRole("button", { name: "Sources" })).toBeDisabled();
  });

  it("shows the sidebar again once hidden", async () => {
    const { onShowSidebar } = renderHeader({ sidebarHidden: true });
    await userEvent.click(screen.getByRole("button", { name: "Show the sidebar" }));
    expect(onShowSidebar).toHaveBeenCalledOnce();
  });

  it("offers no show button while the sidebar is shown", () => {
    renderHeader();
    expect(screen.queryByRole("button", { name: "Show the sidebar" })).not.toBeInTheDocument();
  });

  it("on a phone, opens the questions drawer and starts a new question", async () => {
    const { onOpenDrawer, onNewQuestion } = renderHeader({ compact: true });
    await userEvent.click(screen.getByRole("button", { name: "Open your questions" }));
    await userEvent.click(screen.getByRole("button", { name: "New question" }));
    expect(onOpenDrawer).toHaveBeenCalledOnce();
    expect(onNewQuestion).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Show the sidebar" })).not.toBeInTheDocument();
  });
});
