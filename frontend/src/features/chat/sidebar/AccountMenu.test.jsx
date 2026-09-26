import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../../hooks/useAuth";
import { useTheme } from "../../../hooks/useTheme";
import AccountMenu from "./AccountMenu";

vi.mock("../../../hooks/useAuth");
vi.mock("../../../hooks/useTheme");

let logout;
let setTheme;

beforeEach(() => {
  logout = vi.fn();
  setTheme = vi.fn();
  useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout });
  useTheme.mockReturnValue({ theme: "system", setTheme });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderMenu(props = {}) {
  render(
    <MemoryRouter>
      <AccountMenu {...props} />
    </MemoryRouter>,
  );
}

async function open() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Account menu for alice@example.com" }));
  return user;
}

describe("AccountMenu", () => {
  it("shows the email and its initial", () => {
    renderMenu();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("says who is signed in", async () => {
    renderMenu();
    await open();
    expect(screen.getByText("Signed in as alice@example.com")).toBeInTheDocument();
  });

  it("links to the profile", async () => {
    renderMenu();
    await open();
    expect(screen.getByRole("menuitem", { name: "Profile, ZIP code and date of birth" })).toHaveAttribute("href", "/profile");
  });

  it("offers the theme as a radio group, with the current one checked", async () => {
    renderMenu();
    const user = await open();
    const group = screen.getByRole("radiogroup", { name: "Theme" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "System" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Light" })).toHaveAttribute("aria-checked", "false");
    await user.click(screen.getByRole("radio", { name: "Dark" }));
    expect(setTheme).toHaveBeenCalledWith("dark");
  });

  it("signs out", async () => {
    const onSignOut = vi.fn();
    renderMenu({ onSignOut });
    const user = await open();
    await user.click(screen.getByRole("menuitem", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledOnce();
    expect(onSignOut).toHaveBeenCalledOnce();
  });

  it("lists the shortcuts with Ctrl off a Mac", async () => {
    vi.stubGlobal("navigator", { ...navigator, platform: "Win32" });
    renderMenu();
    await open();
    expect(screen.getByText("Shortcuts: Ctrl K new question, / type a question, Esc close panels")).toBeInTheDocument();
  });

  it("lists the shortcuts with ⌘ on a Mac", async () => {
    vi.stubGlobal("navigator", { ...navigator, platform: "MacIntel" });
    renderMenu();
    await open();
    expect(screen.getByText("Shortcuts: ⌘ K new question, / type a question, Esc close panels")).toBeInTheDocument();
  });

  it("reaches every choice with the arrow keys", async () => {
    renderMenu();
    const user = await open();
    expect(screen.getByRole("menuitem", { name: "Profile, ZIP code and date of birth" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "System" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitem", { name: "Sign out" })).toHaveFocus();
  });
});
