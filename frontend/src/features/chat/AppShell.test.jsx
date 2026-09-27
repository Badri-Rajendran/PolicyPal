import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import AppShell from "./AppShell";

vi.mock("../../hooks/useMediaQuery");

const sidebar = (
  <aside aria-label="Your questions">
    <button type="button">New question</button>
  </aside>
);
const main = <main>The chat</main>;
const panel = <aside aria-label="Sources">Cards</aside>;

beforeEach(() => {
  useMediaQuery.mockReturnValue(false);
});

describe("AppShell", () => {
  it("lays out the sidebar, the main column and the panel", () => {
    const { container } = render(<AppShell sidebar={sidebar} main={main} panel={panel} />);
    expect(screen.getByRole("complementary", { name: "Your questions" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent("The chat");
    expect(screen.getByRole("complementary", { name: "Sources" })).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("shell", "with-panel");
  });

  it("has no panel column without a panel", () => {
    const { container } = render(<AppShell sidebar={sidebar} main={main} panel={null} />);
    expect(container.firstChild).not.toHaveClass("with-panel");
  });

  it("collapses a hidden sidebar out of reach", () => {
    const { container } = render(<AppShell sidebar={sidebar} main={main} sidebarHidden />);
    expect(container.firstChild).toHaveClass("collapsed");
    expect(screen.queryByRole("complementary", { name: "Your questions" })).not.toBeInTheDocument();
    expect(container.querySelector(".side-wrap")).toHaveAttribute("inert");
    expect(container.querySelector(".shell-main")).not.toHaveAttribute("aria-hidden");
  });

  describe("on a phone", () => {
    beforeEach(() => {
      useMediaQuery.mockReturnValue(true);
    });

    it("keeps the sidebar in a closed drawer", () => {
      render(<AppShell sidebar={sidebar} main={main} drawerOpen={false} onCloseDrawer={vi.fn()} />);
      expect(screen.queryByRole("complementary", { name: "Your questions" })).not.toBeInTheDocument();
      expect(screen.getByRole("main")).toBeInTheDocument();
    });

    it("opens the drawer as a dialog, with focus inside", () => {
      render(<AppShell sidebar={sidebar} main={main} drawerOpen onCloseDrawer={vi.fn()} />);
      const drawer = screen.getByRole("dialog", { name: "Your questions" });
      expect(drawer).toContainElement(screen.getByRole("button", { name: "New question" }));
      expect(screen.getByRole("button", { name: "New question" })).toHaveFocus();
    });

    it("closes the drawer from the scrim or Esc", async () => {
      const onCloseDrawer = vi.fn();
      render(<AppShell sidebar={sidebar} main={main} drawerOpen onCloseDrawer={onCloseDrawer} />);
      await userEvent.keyboard("{Escape}");
      expect(onCloseDrawer).toHaveBeenCalledTimes(1);
      await userEvent.click(document.querySelector(".scrim"));
      expect(onCloseDrawer).toHaveBeenCalledTimes(2);
    });

    it("keeps Tab inside the open drawer, and the chat behind it out of reach", async () => {
      const twoButtons = (
        <aside aria-label="Your questions">
          <button type="button">New question</button>
          <button type="button">Profile</button>
        </aside>
      );
      const chat = (
        <main>
          <button type="button">Send</button>
        </main>
      );
      const { container } = render(<AppShell sidebar={twoButtons} main={chat} drawerOpen onCloseDrawer={vi.fn()} />);
      const drawer = screen.getByRole("dialog", { name: "Your questions" });

      for (let i = 0; i < 4; i += 1) {
        await userEvent.tab();
        expect(drawer).toContainElement(document.activeElement);
      }
      await userEvent.tab({ shift: true });
      expect(drawer).toContainElement(document.activeElement);
      expect(container.querySelector(".shell-main")).toHaveAttribute("aria-hidden", "true");
    });

    it("gives the chat back, and focus to what opened the drawer, once it closes", async () => {
      const opener = (
        <main>
          <button type="button">Open your questions</button>
        </main>
      );
      const { container, rerender } = render(<AppShell sidebar={sidebar} main={opener} drawerOpen={false} onCloseDrawer={vi.fn()} />);
      screen.getByRole("button", { name: "Open your questions" }).focus();

      rerender(<AppShell sidebar={sidebar} main={opener} drawerOpen onCloseDrawer={vi.fn()} />);
      expect(screen.getByRole("button", { name: "New question" })).toHaveFocus();
      rerender(<AppShell sidebar={sidebar} main={opener} drawerOpen={false} onCloseDrawer={vi.fn()} />);

      await waitFor(() => expect(screen.getByRole("button", { name: "Open your questions" })).toHaveFocus());
      expect(container.querySelector(".shell-main")).not.toHaveAttribute("aria-hidden");
    });

    it("removes the drawer once closed", async () => {
      const { rerender } = render(<AppShell sidebar={sidebar} main={main} drawerOpen onCloseDrawer={vi.fn()} />);
      rerender(<AppShell sidebar={sidebar} main={main} drawerOpen={false} onCloseDrawer={vi.fn()} />);
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });
  });
});
