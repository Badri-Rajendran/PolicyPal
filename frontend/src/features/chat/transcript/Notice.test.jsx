import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Notice from "./Notice";

describe("Notice", () => {
  it("is a note", () => {
    render(<Notice>These are 2026 plans and prices.</Notice>);
    expect(screen.getByRole("note")).toHaveTextContent("These are 2026 plans and prices.");
  });

  it("links its https address in a new tab, safely", () => {
    render(<Notice>So check Covered California (https://www.coveredca.com/) for them.</Notice>);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "https://www.coveredca.com/");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("links nothing but https", () => {
    render(<Notice>{"Try javascript:alert(1) or http://example.com"}</Notice>);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
