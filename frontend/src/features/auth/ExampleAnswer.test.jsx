import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import ExampleAnswer from "./ExampleAnswer";

describe("ExampleAnswer", () => {
  it("shows a question, its cited answer and the two glossary quotes", () => {
    render(<ExampleAnswer />);
    const example = screen.getByRole("group", { name: "An example answer" });
    expect(within(example).getByRole("heading", { name: "How is coinsurance different from a copay?" })).toBeInTheDocument();
    expect(within(example).getByText(/A copayment is a fixed amount you pay for a covered service, like \$30\./)).toBeInTheDocument();
    expect(within(example).getByText("A fixed amount you pay for a plan-covered service, like $30.")).toBeInTheDocument();
    expect(
      within(example).getByText("A percentage of the cost that you pay for each plan-covered service, like 20%."),
    ).toBeInTheDocument();
    expect(within(example).getAllByText("HealthCare.gov glossary")).toHaveLength(2);
  });

  it("marks the quote a seal points to", async () => {
    render(<ExampleAnswer />);
    const [copayment, coinsurance] = screen.getAllByRole("article");
    await userEvent.click(screen.getByRole("button", { name: "Source 2" }));
    expect(coinsurance).toHaveClass("sel");
    expect(copayment).not.toHaveClass("sel");
    await userEvent.click(screen.getByRole("button", { name: "Source 1" }));
    expect(copayment).toHaveClass("sel");
  });
});
