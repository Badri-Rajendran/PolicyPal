import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Toast from "./Toast";

describe("Toast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the message as a status", () => {
    render(<Toast message="Couldn't rename this thread." onDone={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("Couldn't rename this thread.");
  });

  it("calls onDone after the default 2400 ms", () => {
    const onDone = vi.fn();
    render(<Toast message="Saved" onDone={onDone} />);
    act(() => vi.advanceTimersByTime(2399));
    expect(onDone).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(1));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("honours a custom duration", () => {
    const onDone = vi.fn();
    render(<Toast message="Saved" onDone={onDone} duration={500} />);
    act(() => vi.advanceTimersByTime(500));
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("renders nothing without a message", () => {
    const { container } = render(<Toast message="" onDone={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
