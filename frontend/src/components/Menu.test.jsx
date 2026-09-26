import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import IconButton from "./IconButton";
import Menu, { MenuItem } from "./Menu";

function renderMenu(onRename = vi.fn(), onDelete = vi.fn()) {
  render(
    <>
      <Menu
        label="Options for Deductibles"
        trigger={(props) => (
          <IconButton label="Options for Deductibles" {...props}>
            …
          </IconButton>
        )}
        items={[
          { label: "Rename", onSelect: onRename },
          { label: "Delete", onSelect: onDelete, danger: true },
        ]}
      />
      <button type="button">Elsewhere</button>
    </>,
  );
  return { onRename, onDelete };
}

describe("Menu", () => {
  it("starts closed, with the trigger saying it has a menu", () => {
    renderMenu();
    const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("opens, moves with arrows, selects with Enter, and closes", async () => {
    const user = userEvent.setup();
    const { onDelete } = renderMenu();
    const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu", { name: "Options for Deductibles" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveFocus();
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onDelete).toHaveBeenCalled();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("wraps around with the arrows, and Home and End jump to the ends", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: "Options for Deductibles" }));
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveFocus();
  });

  it("selects with Space and a click", async () => {
    const user = userEvent.setup();
    const { onRename, onDelete } = renderMenu();
    const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
    await user.click(trigger);
    await user.keyboard(" ");
    expect(onRename).toHaveBeenCalledOnce();
    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledOnce();
  });

  it("marks a danger item", async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole("button", { name: "Options for Deductibles" }));
    expect(screen.getByRole("menuitem", { name: "Delete" })).toHaveClass("danger");
  });

  it("closes on Escape without selecting", async () => {
    const user = userEvent.setup();
    const { onRename } = renderMenu();
    const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(onRename).not.toHaveBeenCalled();
    expect(trigger).toHaveFocus();
  });

  it("closes on a click outside, and the trigger toggles it", async () => {
    const user = userEvent.setup();
    renderMenu();
    const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await user.click(trigger);
    await user.click(trigger);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("renders custom content, and a MenuItem in it closes the menu", async () => {
    const user = userEvent.setup();
    const onSignOut = vi.fn();
    render(
      <Menu label="Account" trigger={(props) => <button type="button" {...props}>Account</button>}>
        <p>Signed in as you@example.com</p>
        <MenuItem onSelect={onSignOut}>Sign out</MenuItem>
      </Menu>,
    );
    await user.click(screen.getByRole("button", { name: "Account" }));
    expect(screen.getByText("Signed in as you@example.com")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSignOut).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});
