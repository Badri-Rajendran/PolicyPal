import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import ThreadSearch from "./ThreadSearch";

function Controlled({ onChange = vi.fn() }) {
  const [value, setValue] = useState("");
  return (
    <ThreadSearch
      value={value}
      onChange={(next) => {
        onChange(next);
        setValue(next);
      }}
    />
  );
}

describe("ThreadSearch", () => {
  it("is a labelled search box with its placeholder", () => {
    render(<ThreadSearch value="" onChange={vi.fn()} />);
    const input = screen.getByRole("searchbox", { name: "Search your questions" });
    expect(input).toHaveAttribute("placeholder", "Search your questions");
  });

  it("reports what is typed", async () => {
    const onChange = vi.fn();
    render(<Controlled onChange={onChange} />);
    await userEvent.type(screen.getByRole("searchbox"), "mri");
    expect(onChange).toHaveBeenLastCalledWith("mri");
  });

  it("shows a clear button only with a query, which empties it and refocuses the box", async () => {
    render(<Controlled />);
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
    await userEvent.type(screen.getByRole("searchbox"), "mri");
    await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(screen.getByRole("searchbox")).toHaveValue("");
    expect(screen.getByRole("searchbox")).toHaveFocus();
  });
});
