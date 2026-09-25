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
    sbc_status: "ok",
    ...overrides,
  };
}

function rowFor(name) {
  return screen.getByRole("rowheader", { name: new RegExp(name) }).closest("tr");
}

describe("PlanComparison", () => {
  it("is a captioned table in a scrollable region a keyboard can reach", () => {
    render(<PlanComparison plans={[plan()]} shownAt={SHOWN_AT} />);

    const table = screen.getByRole("table", { name: "2026 Silver plans · Anderson County, TX · shown Sep 18, 2026" });
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

    const link = within(rowFor("CHRISTUS Value Silver 70")).getByRole("link", { name: /Summary of Benefits \(PDF\)/ });
    expect(link).toHaveAttribute("href", "https://example.com/sbc.pdf");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(within(rowFor("Risky Plan")).queryByRole("link")).not.toBeInTheDocument();
  });

  it("says in each plan's row whether its Summary of Benefits was read", () => {
    render(
      <PlanComparison
        plans={[plan(), plan({ hios_plan_id: "x2", name: "Oscar Silver Classic", sbc_status: "blocked" })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(within(rowFor("CHRISTUS Value Silver 70")).getByText("Summary of Benefits read")).toBeInTheDocument();
    const blocked = screen.getByRole("rowheader", { name: /Oscar Silver Classic/ });
    expect(blocked).toHaveTextContent("Summary of Benefits not read here: the insurer blocks automated access");
  });

  it("says when only part of a plan's Summary of Benefits was read, and still counts it as read", () => {
    render(
      <PlanComparison
        plans={[plan(), plan({ hios_plan_id: "x2", name: "U Health Plus", sbc_status: "partial" })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(
      screen.getByText("Summary of Benefits only partly read here: its costs chart is not all there"),
    ).toBeInTheDocument();
    expect(within(rowFor("U Health Plus")).getByRole("link", { name: /Summary of Benefits \(PDF\)/ })).toBeInTheDocument();
    expect(screen.queryByText(/have no Summary of Benefits read here/)).not.toBeInTheDocument();
  });

  it("keeps the link to the insurer's PDF when the document couldn't be read here", () => {
    render(<PlanComparison plans={[plan({ sbc_status: "not_pdf" })]} shownAt={SHOWN_AT} />);

    expect(screen.getByText("Summary of Benefits not read here: the link returned a web page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Summary of Benefits \(PDF\)/ })).toHaveAttribute(
      "href", "https://example.com/sbc.pdf",
    );
  });

  it("says a plan lists no Summary of Benefits, with nothing to link", () => {
    render(<PlanComparison plans={[plan({ sbc_status: "no_link", benefits_url: null })]} shownAt={SHOWN_AT} />);

    expect(screen.getByText("No Summary of Benefits listed")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Summary of Benefits/ })).not.toBeInTheDocument();
  });

  it("counts the plans it has no Summary of Benefits for beneath the table", () => {
    render(
      <PlanComparison
        plans={[plan(), plan({ hios_plan_id: "x2", sbc_status: "blocked" }), plan({ hios_plan_id: "x3", sbc_status: "not_read" })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(
      screen.getByText("2 of these 3 plans have no Summary of Benefits read here, so their coverage can't be answered from one."),
    ).toBeInTheDocument();
  });

  it("shows no status or count for a card saved before statuses were recorded", () => {
    render(<PlanComparison plans={[plan({ sbc_status: null }), plan({ hios_plan_id: "x2", sbc_status: undefined })]} shownAt={SHOWN_AT} />);

    expect(screen.queryByText(/Summary of Benefits read|not read here|no Summary of Benefits/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Summary of Benefits \(PDF\)/ })).toHaveLength(2);
  });

  it("points to HealthCare.gov for today's prices", () => {
    render(<PlanComparison plans={[plan()]} shownAt={SHOWN_AT} />);

    expect(screen.getByRole("link", { name: /HealthCare.gov/ })).toHaveAttribute("href", "https://www.healthcare.gov/see-plans/");
    expect(screen.getByText(/before any tax credit/)).toBeInTheDocument();
  });

  it("leaves the county out of the caption when plans come from several", () => {
    render(<PlanComparison plans={[plan(), plan({ hios_plan_id: "x2", county_name: "Tulsa", state: "OK", metal_level: "Gold" })]} shownAt={SHOWN_AT} />);

    expect(screen.getByRole("table", { name: "2026 plans · shown Sep 18, 2026" })).toBeInTheDocument();
  });

  it("leaves the plan year out when the plans' years differ", () => {
    render(
      <PlanComparison plans={[plan(), plan({ hios_plan_id: "x2", plan_year: 2027 })]} shownAt={SHOWN_AT} />,
    );

    expect(screen.getByRole("table", { name: "Silver plans · Anderson County, TX · shown Sep 18, 2026" })).toBeInTheDocument();
  });

  it("names Covered California and CMS's filed rates for California plans", () => {
    render(
      <PlanComparison
        plans={[plan({ state: "CA", county_name: "Los Angeles", quality_rating: null, premium_reference: null })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(screen.getByRole("table", { name: /^2026 Silver plans · Los Angeles County, CA/ })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Covered California/ });
    expect(link).toHaveAttribute("href", "https://www.coveredca.com/");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/CMS's published 2026 rates for the age shown/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /HealthCare\.gov/ })).not.toBeInTheDocument();
    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("Not available");
    expect(rowFor("CHRISTUS Value Silver 70")).not.toHaveTextContent("Not rated");
  });

  it("keeps 'Not rated' and the tax-credit wording for other states", () => {
    render(<PlanComparison plans={[plan({ quality_rating: null })]} shownAt={SHOWN_AT} />);

    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("Not rated");
    expect(screen.getByText(/before any tax credit, which may lower what you pay/)).toBeInTheDocument();
  });

  it("says a California plan with no filed rate for the ZIP is unpriced, not that a live price failed", () => {
    render(
      <PlanComparison
        plans={[plan({ state: "CA", monthly_premium: null, premium_age: null, premium_reference: null })]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(rowFor("CHRISTUS Value Silver 70")).toHaveTextContent("No filed rate for this ZIP code");
    expect(screen.queryByText("Live price unavailable")).not.toBeInTheDocument();
  });

  it("describes each exchange's premiums when one answer mixes California and HealthCare.gov plans", () => {
    render(
      <PlanComparison
        plans={[
          plan({ hios_plan_id: "ca1", name: "Kaiser Silver 70", state: "CA", county_name: "Los Angeles" }),
          plan({ hios_plan_id: "az1", name: "Arizona Silver", state: "AZ", county_name: "Maricopa" }),
        ]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(
      screen.getByText(
        /Premiums for plans sold on Covered California are CMS's published 2026 rates .*; the others are before any tax credit/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Covered California/ })).toHaveAttribute("href", "https://www.coveredca.com/");
    expect(screen.getByRole("link", { name: /HealthCare\.gov/ })).toHaveAttribute(
      "href",
      "https://www.healthcare.gov/see-plans/",
    );
    expect(rowFor("Kaiser Silver 70")).toHaveTextContent("3 of 5");
  });

  it("does not depend on which state's plan comes first", () => {
    render(
      <PlanComparison
        plans={[
          plan({ hios_plan_id: "az1", name: "Arizona Silver", state: "AZ", county_name: "Maricopa" }),
          plan({ hios_plan_id: "ca1", name: "Kaiser Silver 70", state: "CA", county_name: "Los Angeles" }),
        ]}
        shownAt={SHOWN_AT}
      />,
    );

    expect(screen.getByText(/plans sold on Covered California are CMS's published 2026 rates/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /opens in a new tab/ }).map((a) => a.textContent)).toEqual(
      expect.arrayContaining(["HealthCare.gov (opens in a new tab)", "Covered California (opens in a new tab)"]),
    );
  });
});
