import { formatMoney } from "../../utils/formatMoney";
import { safeUrl } from "../../utils/safeUrl";
import { exchangeFor } from "./exchanges";
import { isUnreadable, sbcNote } from "./sbcStatus";

const REFERENCE_AGE = 27;

function caption(plans, shownAt) {
  const levels = new Set(plans.map((p) => p.metal_level));
  const years = new Set(plans.map((p) => p.plan_year));
  const places = new Set(plans.map((p) => `${p.county_name} County, ${p.state}`));
  const shown = new Date(shownAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const noun = levels.size === 1 ? `${[...levels][0]} plans` : "plans";
  return [
    years.size === 1 ? `${[...years][0]} ${noun}` : noun.charAt(0).toUpperCase() + noun.slice(1),
    places.size === 1 ? [...places][0] : null,
    `shown ${shown}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

function unreadableNote(plans) {
  const count = plans.filter((p) => isUnreadable(p.sbc_status)).length;
  if (count === 0) return null;
  const one = count === 1;
  return `${count} of these ${plans.length} plans ${one ? "has" : "have"} no Summary of Benefits read here, so ${
    one ? "its" : "their"
  } coverage can't be answered from one.`;
}

// Each exchange whose plans are in the table, with a plan year for its filed rates.
// One answer can hold several searches, e.g. a California and an Arizona ZIP.
function exchangesIn(plans) {
  const found = new Map();
  for (const plan of plans) {
    const exchange = exchangeFor(plan.state);
    if (!found.has(exchange.name)) found.set(exchange.name, { ...exchange, year: plan.plan_year });
  }
  return [...found.values()];
}

function premiumNote(exchanges) {
  const filed = exchanges.filter((e) => e.filedRates);
  const live = exchanges.filter((e) => !e.filedRates);
  const filedNote = (e) =>
    `CMS's published ${e.year} rates for the age shown, before any federal tax credit or state premium help`;
  if (live.length === 0 && filed.length === 1) return `Premiums are ${filedNote(filed[0])}.`;
  if (filed.length === 0) return "Premiums are before any tax credit, which may lower what you pay.";
  const parts = filed.map((e) => `premiums for plans sold on ${e.name} are ${filedNote(e)}`);
  if (live.length) parts.push("the others are before any tax credit, which may lower what you pay");
  const sentence = parts.join("; ");
  return `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.`;
}

function Premium({ plan }) {
  if (plan.monthly_premium === null) {
    // A filed-rate plan has no live price to be unavailable: CMS lists no rating area for the ZIP.
    if (exchangeFor(plan.state).filedRates) return <span>No filed rate for this ZIP code</span>;
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
  const unreadable = unreadableNote(plans);
  const exchanges = exchangesIn(plans);

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
              const note = sbcNote(plan.sbc_status);
              return (
                <tr key={plan.hios_plan_id}>
                  <th scope="row">
                    <span className="plan-name">{plan.name}</span>
                    <span className="plan-sub">
                      {plan.issuer} · {plan.metal_level} · {plan.plan_type}
                    </span>
                    {note && <span className="plan-sub">{note}</span>}
                    {summary && (
                      <a href={summary} target="_blank" rel="noopener noreferrer">
                        Summary of Benefits (PDF)
                        <span className="visually-hidden"> for {plan.name} (opens in a new tab)</span>
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
                  <td>
                    {plan.quality_rating !== null
                      ? `${plan.quality_rating} of 5`
                      : exchangeFor(plan.state).filedRates
                        ? "Not available"
                        : "Not rated"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {unreadable && <p className="plan-footnote">{unreadable}</p>}
      <p className="plan-footnote">
        {premiumNote(exchanges)} Plans and prices change, so check today's at{" "}
        {exchanges.map((exchange, i) => (
          <span key={exchange.name}>
            {i > 0 && " and "}
            <a href={exchange.url} target="_blank" rel="noopener noreferrer">
              {exchange.name}
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          </span>
        ))}
        .
      </p>
    </section>
  );
}
