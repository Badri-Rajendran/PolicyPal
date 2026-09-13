import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../../hooks/useAuth";
import Sidebar from "./Sidebar";

vi.mock("../../hooks/useAuth");

const threads = [
  { id: "t1", title: "Deductibles" },
  { id: "t2", title: "Auto claims" },
];

describe("Sidebar", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout: vi.fn() });
  });

  it("shows a loading hint while threads load", () => {
    render(<Sidebar threads={[]} status="loading" onSelect={() => {}} onDelete={() => {}} onCreate={() => {}} />);
    expect(screen.getByText("Loading your questions…")).toBeInTheDocument();
  });

  it("shows an empty hint when there are no threads", () => {
    render(<Sidebar threads={[]} status="ready" onSelect={() => {}} onDelete={() => {}} onCreate={() => {}} />);
    expect(screen.getByText("Your questions will show up here.")).toBeInTheDocument();
  });

  it("lists every thread", () => {
    render(<Sidebar threads={threads} status="ready" onSelect={() => {}} onDelete={() => {}} onCreate={() => {}} />);
    expect(screen.getByRole("button", { name: "Deductibles" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Auto claims" })).toBeInTheDocument();
  });

  it("calls onCreate from the new question button", async () => {
    const onCreate = vi.fn();
    render(<Sidebar threads={[]} status="ready" onSelect={() => {}} onDelete={() => {}} onCreate={onCreate} />);
    await userEvent.click(screen.getByRole("button", { name: "New question" }));
    expect(onCreate).toHaveBeenCalledOnce();
  });

  it("shows the signed-in user's email and signs them out", async () => {
    const logout = vi.fn();
    useAuth.mockReturnValue({ user: { email: "alice@example.com" }, logout });
    render(<Sidebar threads={[]} status="ready" onSelect={() => {}} onDelete={() => {}} onCreate={() => {}} />);

    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledOnce();
  });
});
