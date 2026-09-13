import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ErrorBanner from "./ErrorBanner";

describe("ErrorBanner", () => {
  it("renders nothing when there is no message", () => {
    const { container } = render(<ErrorBanner>{""}</ErrorBanner>);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the message as an alert", () => {
    render(<ErrorBanner>Something went wrong.</ErrorBanner>);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong.");
  });
});
