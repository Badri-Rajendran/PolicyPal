import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ThinkingIndicator from "./ThinkingIndicator";

describe("ThinkingIndicator", () => {
  it("announces itself to assistive tech", () => {
    render(<ThinkingIndicator />);
    expect(screen.getByRole("status")).toHaveAccessibleName(/looking through your policy documents/i);
  });
});
