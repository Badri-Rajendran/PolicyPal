import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PlanRef from "./PlanRef";

describe("PlanRef", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.replaceChildren();
  });

  it("shows the plan's number and name", () => {
    render(
      <PlanRef position={1} messageId="a1" name="Sharp Silver 70 Premier HMO">
        Sharp Silver 70 Premier HMO
      </PlanRef>,
    );
    const button = screen.getByRole("button", { name: "Plan 1, Sharp Silver 70 Premier HMO" });
    expect(button).toHaveTextContent("1Sharp Silver 70 Premier HMO");
    expect(button).toHaveClass("planref");
  });

  it("scrolls to its row and flashes it for 1.4 s", () => {
    const row = document.createElement("tr");
    row.id = "plan-a1-2";
    row.scrollIntoView = vi.fn();
    document.body.appendChild(row);
    render(
      <PlanRef position={2} messageId="a1" name="Silver 70 HMO">
        Silver 70 HMO
      </PlanRef>,
    );

    act(() => screen.getByRole("button").click());

    expect(row.scrollIntoView).toHaveBeenCalled();
    expect(row).toHaveClass("flash");
    act(() => vi.advanceTimersByTime(1399));
    expect(row).toHaveClass("flash");
    act(() => vi.advanceTimersByTime(1));
    expect(row).not.toHaveClass("flash");
  });

  it("does nothing when its row isn't on the page", () => {
    render(
      <PlanRef position={3} messageId="a1" name="Gone">
        Gone
      </PlanRef>,
    );
    expect(() => act(() => screen.getByRole("button").click())).not.toThrow();
  });
});
