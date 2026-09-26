import { render as renderInPage, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../../hooks/useAuth";
import Sidebar from "./Sidebar";

vi.mock("../../../hooks/useAuth");

// The account menu links to /profile, and a Link needs a router.
const render = (ui) => renderInPage(<MemoryRouter>{ui}</MemoryRouter>);

const threads = [
  { id: "t1", title: "Is an MRI covered by my plan?", updated_at: "2026-09-26T14:00:00" },
  { id: "t2", title: "Copay vs coinsurance", updated_at: "2026-09-26T09:00:00" },
  { id: "t3", title: "MRI cost on bronze plans", updated_at: "2026-08-01T09:00:00" },
];

function renderSidebar(props = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onCreate: vi.fn(),
    onDelete: vi.fn(),
    onRename: vi.fn(),
    onHide: vi.fn(),
  };
  render(<Sidebar threads={threads} status="ready" selectedThreadId="t2" {...handlers} {...props} />);
  return handlers;
}

describe("Sidebar", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 8, 26, 15, 0));
    useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn() });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("is a labelled landmark with the brand", () => {
    renderSidebar();
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
    expect(screen.getByText("PolicyPal")).toBeInTheDocument();
  });

  it("shows a loading hint while threads load", () => {
    renderSidebar({ threads: [], status: "loading" });
    expect(screen.getByText("Loading your questions…")).toBeInTheDocument();
  });

  it("shows an empty hint when there are no threads", () => {
    renderSidebar({ threads: [] });
    expect(screen.getByText("Your questions will show up here.")).toBeInTheDocument();
  });

  it("groups threads under date headings", () => {
    renderSidebar();
    const today = screen.getByRole("region", { name: "Today" });
    expect(within(today).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "Earlier" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Previous 7 days" })).not.toBeInTheDocument();
  });

  it("marks the selected thread", () => {
    renderSidebar();
    expect(screen.getByRole("button", { name: "Copay vs coinsurance" })).toHaveAttribute("aria-current", "page");
  });

  it("filters by search, case-insensitively, and highlights the matches", async () => {
    const user = userEvent.setup();
    const { container } = renderInPage(
      <MemoryRouter>
        <Sidebar threads={threads} status="ready" selectedThreadId={null} onSelect={vi.fn()} onCreate={vi.fn()} onDelete={vi.fn()} onRename={vi.fn()} onHide={vi.fn()} />
      </MemoryRouter>,
    );
    await user.type(screen.getByRole("searchbox", { name: "Search your questions" }), "mri");
    expect(screen.getByRole("heading", { name: "2 questions match" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copay vs coinsurance" })).not.toBeInTheDocument();
    expect([...container.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["MRI", "MRI"]);
  });

  it("says when nothing matches, and clearing restores the list", async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.type(screen.getByRole("searchbox"), "dental");
    expect(screen.getByText("No questions match")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByRole("heading", { name: "Today" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("says one question matches in the singular", async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.type(screen.getByRole("searchbox"), "copay");
    expect(screen.getByRole("heading", { name: "1 question matches" })).toBeInTheDocument();
  });

  it("calls onCreate from the new question button, which names its shortcut", async () => {
    const user = userEvent.setup();
    const { onCreate } = renderSidebar();
    const button = screen.getByRole("button", { name: "New question" });
    expect(button).toHaveAttribute("aria-keyshortcuts", "Control+K Meta+K");
    await user.click(button);
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("hides itself", async () => {
    const user = userEvent.setup();
    const { onHide } = renderSidebar();
    await user.click(screen.getByRole("button", { name: "Hide the sidebar" }));
    expect(onHide).toHaveBeenCalledOnce();
  });

  it("selects, renames and deletes threads", async () => {
    const user = userEvent.setup();
    const { onSelect, onRename, onDelete } = renderSidebar();
    await user.click(screen.getByRole("button", { name: "Copay vs coinsurance" }));
    expect(onSelect).toHaveBeenCalledWith("t2");

    await user.click(screen.getByRole("button", { name: "Options for Copay vs coinsurance" }));
    await user.click(screen.getByRole("menuitem", { name: "Rename" }));
    await user.type(screen.getByRole("textbox", { name: "Thread name" }), "!{Enter}");
    expect(onRename).toHaveBeenCalledWith("t2", "Copay vs coinsurance!");

    await user.click(screen.getByRole("button", { name: "Options for Copay vs coinsurance" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledWith("t2");
  });

  it("shows the account menu", () => {
    renderSidebar();
    expect(screen.getByRole("button", { name: "Account menu for alice@example.com" })).toBeInTheDocument();
  });
});
