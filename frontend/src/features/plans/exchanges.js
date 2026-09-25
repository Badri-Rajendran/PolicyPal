// The exchange that sells a state's plans. Mirrors src/core/exchanges.py; a
// test on each side pins California to Covered California (ADR 0024).
// `filedRates`: premiums are CMS's published rates, not a live price.
const HEALTHCARE_GOV = { name: "HealthCare.gov", url: "https://www.healthcare.gov/see-plans/", filedRates: false };

const OWN_EXCHANGES = {
  CA: { name: "Covered California", url: "https://www.coveredca.com/", filedRates: true },
};

export function exchangeFor(state) {
  return OWN_EXCHANGES[state] ?? HEALTHCARE_GOV;
}
