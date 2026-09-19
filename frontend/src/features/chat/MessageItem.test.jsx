import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MessageItem from "./MessageItem";

describe("MessageItem", () => {
  it("labels a user message as You", () => {
    render(
      <MessageItem message={{ id: "1", role: "user", content: "What is a deductible?", created_at: "2026-01-01T00:00:00Z" }} />,
    );
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("What is a deductible?")).toBeInTheDocument();
  });

  it("labels an assistant message as PolicyPal", () => {
    render(
      <MessageItem
        message={{ id: "2", role: "assistant", content: "It's the amount you pay first.", created_at: "2026-01-01T00:00:00Z" }}
      />,
    );
    expect(screen.getByText("PolicyPal")).toBeInTheDocument();
  });

  it("renders sources as a footnote list with relevance percentages", () => {
    render(
      <MessageItem
        message={{
          id: "3",
          role: "assistant",
          content: "It's the amount you pay first.",
          created_at: "2026-01-01T00:00:00Z",
          sources: [{ source: "wiki_Health_insurance.txt", chunk_id: "c1", relevance: 0.958 }],
        }}
      />,
    );
    expect(screen.getByText("Health insurance")).toBeInTheDocument();
    expect(screen.getByText("96% match")).toBeInTheDocument();
  });

  it("omits the sources section when there are none", () => {
    render(
      <MessageItem message={{ id: "4", role: "assistant", content: "Hi", created_at: "2026-01-01T00:00:00Z", sources: [] }} />,
    );
    expect(screen.queryByText("Sources")).not.toBeInTheDocument();
  });

  it("shows an assistant answer's plans as a comparison table", () => {
    const plans = [{
      hios_plan_id: "p1", plan_year: 2026, name: "Value Silver", issuer: "CHRISTUS", metal_level: "Silver", plan_type: "HMO",
      monthly_premium: "620.15", premium_age: 34, premium_reference: "535.35", deductible: "5990.00", drug_deductible: null,
      out_of_pocket_max: "5990.00", hsa_eligible: false, quality_rating: 3, county_name: "Anderson", state: "TX", benefits_url: null,
    }];
    render(<MessageItem message={{ id: "5", role: "assistant", content: "Here they are.", created_at: "2026-09-18T15:00:00Z", plans }} />);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: /Value Silver/ })).toBeInTheDocument();
  });

  it("links an https address in an answer, keeping the text around it", () => {
    const content = "Read the full summary at https://example.com/sbc.pdf. It has the details.";
    render(<MessageItem message={{ id: "7", role: "assistant", content, created_at: "2026-01-01T00:00:00Z" }} />);

    const link = screen.getByRole("link", { name: /example\.com\/sbc\.pdf/ });
    expect(link).toHaveAttribute("href", "https://example.com/sbc.pdf");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link.closest("p")).toHaveTextContent(/^Read the full summary at .*\. It has the details\.$/);
  });

  it("never links anything but https", () => {
    const content = "Try javascript:alert(1) or http://example.com";
    render(<MessageItem message={{ id: "8", role: "assistant", content, created_at: "2026-01-01T00:00:00Z" }} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByText(content)).toBeInTheDocument();
  });

  it("leaves a user's own message unlinked", () => {
    const content = "Is https://example.com/sbc.pdf right?";
    render(<MessageItem message={{ id: "9", role: "user", content, created_at: "2026-01-01T00:00:00Z" }} />);

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows no table for an answer without plans", () => {
    render(<MessageItem message={{ id: "6", role: "assistant", content: "Hi", created_at: "2026-01-01T00:00:00Z", plans: [] }} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
