import { formatMoney } from "../../utils/formatMoney";
import { safeUrl } from "../../utils/safeUrl";

const REFERENCE_AGE = 27;
const HEALTHCARE_GOV = "https://www.healthcare.gov/see-plans/";

function caption(plans, shownAt) {
  const levels = new Set(plans.map((p) => p.metal_level));
  const places = new Set(plans.map((p) => `${p.county_name} County, ${p.state}`));
  const shown = new Date(shownAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  return [
    levels.size === 1 ? `${[...levels][0]} plans` : "Plans",
    places.size === 1 ? [...places][0] : null,
    `shown ${shown}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function Premium({ plan }) {
  if (plan.monthly_premium === null) {
    return (
      <>
        <span>Live price unavailable</span>
        {plan.premium_reference !== null && (
          <span className="plan-sub">
            {formatMoney(plan.premium_reference, { cents: true })}/mo at age {REFERENCE_AGE}
          </span>
        )}
      </>
    );
  }
  return (
    <>
      <span className="plan-figure">{formatMoney(plan.monthly_premium, { cents: true })}/mo</span>
      <span className="plan-sub">
        {plan.premium_age === null ? "for the age you asked about" : `age ${plan.premium_age}`}
      </span>
    </>
  );
}

function Deductible({ plan }) {
  if (plan.drug_deductible !== null) {
    return (
      <>
        <span>{formatMoney(plan.deductible) ?? "Not listed"} medical</span>
        <span>{formatMoney(plan.drug_deductible)} drugs</span>
      </>
    );
  }
  return <span>{formatMoney(plan.deductible) ?? "Not listed"}</span>;
}

export default function PlanComparison({ plans, shownAt }) {
  const title = caption(plans, shownAt);

  return (
    <section className="plan-comparison">
      <div className="plan-table-scroll" role="region" aria-label={`${title}, scrolls sideways`} tabIndex={0}>
        <table className="plan-table">
          <caption>{title}</caption>
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Premium</th>
              <th scope="col">Deductible</th>
              <th scope="col">Out-of-pocket max</th>
              <th scope="col">Quality rating</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((plan) => {
              const summary = safeUrl(plan.benefits_url);
              return (
                <tr key={plan.hios_plan_id}>
                  <th scope="row">
                    <span className="plan-name">{plan.name}</span>
                    <span className="plan-sub">
                      {plan.issuer} · {plan.metal_level} · {plan.plan_type}
                    </span>
                    {summary && (
                      <a href={summary} target="_blank" rel="noopener noreferrer">
                        Plan summary<span className="visually-hidden"> for {plan.name} (opens in a new tab)</span>
                      </a>
                    )}
                  </th>
                  <td>
                    <Premium plan={plan} />
                  </td>
                  <td>
                    <Deductible plan={plan} />
                  </td>
                  <td>{formatMoney(plan.out_of_pocket_max) ?? "Not listed"}</td>
                  <td>{plan.quality_rating === null ? "Not rated" : `${plan.quality_rating} of 5`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="plan-footnote">
        Premiums are before any tax credit, which may lower what you pay. Plans and prices change, so check
        today's at{" "}
        <a href={HEALTHCARE_GOV} target="_blank" rel="noopener noreferrer">
          HealthCare.gov<span className="visually-hidden"> (opens in a new tab)</span>
        </a>
        .
      </p>
    </section>
  );
}
