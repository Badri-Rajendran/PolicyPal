import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PlanComparison from "./PlanComparison";

const SHOWN_AT = "2026-09-18T15:00:00Z";

function plan(overrides) {
  return {
    hios_plan_id: "66252TX0380010",
    plan_year: 2026,
    name: "CHRISTUS Value Silver 70",
    issuer: "CHRISTUS Health Plan",
    metal_level: "Silver",
    plan_type: "HMO",
    monthly_premium: "620.15",
    premium_age: 34,
    premium_reference: "535.35",
    deductible: "5990.00",
    drug_deductible: null,
    out_of_pocket_max: "5990.00",
    hsa_eligible: false,
    quality_rating: 3,
    county_name: "Anderson",
    state: "TX",
    benefits_url: "https://example.com/sbc.pdf",
    ...overrides,
  };
}

function rowFor(name) {
  return screen.getByRole("rowheader", { name: new RegExp(name) }).closest("tr");
}

describe("PlanComparison", () => {
  it("is a captioned table in a scrollable region a keyboard can reach", () => {
    render(<PlanComparison plans={[plan()]} shownAt={SHOWN_AT} />);

    const table = screen.getByRole("table", { name: "Silver plans · Anderson County, TX · shown Sep 18, 2026" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Plan", "Premium", "Deductible", "Out-of-pocket max", "Quality rating",
    ]);
    expect(screen.getByRole("region", { name: /scrolls sideways/ })).toHaveAttribute("tabindex", "0");
  });

  it("shows a live premium with the age it was priced for", () => {
    render(<PlanComparison plans={[plan()]} shownAt={SHOWN_AT} />);

    const row = rowFor("CHRISTUS Value Silver 70");
    expect(within(row).getByText("$620.15/mo")).toBeInTheDocument();
    expect(within(row).getByText("age 34")).toBeInTheDocument();
    expect(within(row).getByText("3 of 5")).toBeInTheDocument();
  });

  it("never names a child's age, only that the price is for the age asked about", () => {
    render(<PlanComparison plans={[plan({ monthly_premium: "255.53", premium_age: null })]} shownAt={SHOWN_AT} />);

    expect(screen.getByText("$255.53/mo")).toBeInTheDocument();
    expect(screen.getByText("for the age you asked about")).toBeInTheDocument();
  });

  it("never passes an unpriced plan off as a live price", () => {
    render(<PlanComparison plans={[plan({ monthly_premium: null, premium_age: null })]} shownAt={SHOWN_AT} />);

    expect(screen.getByText("Live price unavailable")).toBeInTheDocument();
    expect(screen.getByText("$535.35/mo at age 27")).toBeInTheDocument();
    expect(screen.queryByText("$535.35/mo")).not.toBeInTheDocument();
  });

  it("shows both deductibles when a plan has separate medical and drug ones", () => {
    render(<PlanComparison plans={[plan({ deductible: "0.00", drug_deductible: "5500.00" })]} shownAt={SHOWN_AT} />);

    expect(screen.getByText("$0 medical")).toBeInTheDocument();
    expect(screen.getByText("$5,500 drugs")).toBeInTheDocument();
  });

  it("says what is missing rather than leaving a blank", () => {
    render(
      <PlanComparison plans={[plan({ quality_rating: null, out_of_pocket_max: null, deductible: null })]} shownAt={SHOWN_AT} />,
    );

    expect(screen.getByText("Not rated")).toBeInTheDocument();
    expect(screen.getAllByText("Not listed")).toHaveLength(2);
  });

  it("links a plan summary safely, and not at all when the address is unsafe", () => {
    render(
      <PlanComparison
        plans={[plan(), plan({ hios_plan_id: "x2", name: "Risky Plan", benefits_url: "javascript:alert(1)" })]}
        shownAt={SHOWN_AT}
      />,
    );

    const link = within(rowFor("CHRISTUS Value Silver 70")).getByRole("link", { name: /Plan summary/ });
    expect(link).toHaveAttribute("href", "https://example.com/sbc.pdf");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(rowFor("Risky Plan")).queryByRole("link")).not.toBeInTheDocument();
  });

  it("points to HealthCare.gov for today's prices", () => {
    render(<PlanComparison plans={[plan()]} shownAt={SHOWN_AT} />);

    expect(screen.getByRole("link", { name: /HealthCare.gov/ })).toHaveAttribute("href", "https://www.healthcare.gov/see-plans/");
    expect(screen.getByText(/before any tax credit/)).toBeInTheDocument();
  });

  it("leaves the county out of the caption when plans come from several", () => {
    render(<PlanComparison plans={[plan(), plan({ hios_plan_id: "x2", county_name: "Tulsa", state: "OK", metal_level: "Gold" })]} shownAt={SHOWN_AT} />);

    expect(screen.getByRole("table", { name: "Plans · shown Sep 18, 2026" })).toBeInTheDocument();
  });
});
