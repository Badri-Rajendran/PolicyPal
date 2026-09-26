import { ExternalLink, MessageSquare } from "lucide-react";
import { useId } from "react";
import { formatMoney } from "../../utils/formatMoney";
import { safeUrl } from "../../utils/safeUrl";
import { exchangeFor } from "./exchanges";
import { isUnreadable, sbcNote } from "./sbcStatus";

const REFERENCE_AGE = 27;

// The head's three parts: "2026 Silver plans", the place, and the date shown.
function heading(plans, shownAt) {
  const levels = new Set(plans.map((p) => p.metal_level));
  const years = new Set(plans.map((p) => p.plan_year));
  const places = new Set(plans.map((p) => `${p.county_name} County, ${p.state}`));
  const shown = new Date(shownAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  const noun = levels.size === 1 ? `${[...levels][0]} plans` : "plans";
  return {
    title: years.size === 1 ? `${[...years][0]} ${noun}` : noun.charAt(0).toUpperCase() + noun.slice(1),
    place: places.size === 1 ? [...places][0] : null,
    shown: `Shown ${shown}`,
  };
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
    if (exchangeFor(plan.state).filedRates) return <span className="sub">No filed rate for this ZIP code</span>;
    return (
      <>
        <span className="sub">Live price unavailable</span>
        {plan.premium_reference !== null && (
          <span className="sub">
            {formatMoney(plan.premium_reference, { cents: true })}/mo at age {REFERENCE_AGE}
          </span>
        )}
      </>
    );
  }
  return (
    <>
      <span className="fig">{formatMoney(plan.monthly_premium, { cents: true })}/mo</span>
      <span className="sub">{plan.premium_age === null ? "for the age you asked about" : `age ${plan.premium_age}`}</span>
    </>
  );
}

function Money({ amount }) {
  const text = formatMoney(amount);
  return text ? <span className="fig">{text}</span> : <span className="sub">Not listed</span>;
}

function Deductible({ plan }) {
  if (plan.drug_deductible !== null) {
    return (
      <>
        <Money amount={plan.deductible} /> <span className="sub">medical</span>
        <span className="fig drug">{formatMoney(plan.drug_deductible)}</span> <span className="sub">drugs</span>
      </>
    );
  }
  return <Money amount={plan.deductible} />;
}

function Quality({ plan }) {
  if (plan.quality_rating !== null) return <span className="fig">{plan.quality_rating} of 5</span>;
  return <span className="sub">{exchangeFor(plan.state).filedRates ? "Not available" : "Not rated"}</span>;
}

// The plans an answer showed, numbered 1…n in the order it showed them
// (Main.dc.html's .plans). It compares; nothing marks a "best" plan (ADR 0010).
export default function PlanComparison({ plans, shownAt, messageId, onAskAboutPlan }) {
  const { title, place, shown } = heading(plans, shownAt);
  const titleId = useId();
  const unreadable = unreadableNote(plans);
  const exchanges = exchangesIn(plans);

  return (
    <section className="plans">
      <div className="plans-head">
        <h3 id={titleId}>{title}</h3>
        {place && <span>{place}</span>}
        <span className="plans-shown">{shown}</span>
      </div>
      <div className="plans-scroll" role="region" aria-label={`${title}, scrolls sideways`} tabIndex={0}>
        <table aria-labelledby={titleId}>
          <thead>
            <tr>
              <th className="pos" scope="col">
                <span className="visually-hidden">Number</span>
              </th>
              <th scope="col">Plan</th>
              <th scope="col">Premium</th>
              <th scope="col">Deductible</th>
              <th scope="col">Out-of-pocket max</th>
              <th scope="col">Quality rating</th>
            </tr>
          </thead>
          <tbody>
            {plans.map((plan, index) => {
              const position = index + 1;
              const summary = safeUrl(plan.benefits_url);
              const note = sbcNote(plan.sbc_status);
              return (
                <tr key={plan.hios_plan_id} id={messageId ? `plan-${messageId}-${position}` : undefined}>
                  <td className="pos">
                    <span>{position}</span>
                  </td>
                  <th scope="row">
                    <span className="pname">{plan.name}</span>
                    <span className="psub">
                      <i className="metal" data-metal={plan.metal_level?.toLowerCase()} aria-hidden="true" />
                      {[plan.issuer, plan.metal_level, plan.plan_type].filter(Boolean).join(", ")}
                    </span>
                    {note && <span className="sub">{note}</span>}
                    {(onAskAboutPlan || summary) && (
                      <div className="rowacts">
                        {onAskAboutPlan && (
                          <button type="button" onClick={() => onAskAboutPlan(position, plan.name)}>
                            <MessageSquare className="i sm" aria-hidden="true" />
                            Ask about this plan
                            <span className="visually-hidden">: {plan.name}</span>
                          </button>
                        )}
                        {summary && (
                          <a href={summary} target="_blank" rel="noopener noreferrer">
                            <ExternalLink className="i sm" aria-hidden="true" />
                            Summary of Benefits{" "}
                            <span className="visually-hidden">(PDF) for {plan.name} (opens in a new tab)</span>
                          </a>
                        )}
                      </div>
                    )}
                  </th>
                  <td>
                    <Premium plan={plan} />
                  </td>
                  <td>
                    <Deductible plan={plan} />
                  </td>
                  <td>
                    <Money amount={plan.out_of_pocket_max} />
                  </td>
                  <td>
                    <Quality plan={plan} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="plans-foot">
        {unreadable && <p>{unreadable}</p>}
        <p>
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
      </div>
    </section>
  );
}
