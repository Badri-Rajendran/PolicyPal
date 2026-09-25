# 0024 — California plans come from CMS's state-based exchange PUF, priced from filed rates

## Status

Accepted. Amends ADR 0009 (a second pipeline writes the plan catalog) and ADR
0010 (California premiums come from filed rates, not the live API).

## Context

A user with a California ZIP got "not a marketplace state", and the model sent
them to HealthCare.gov. That is the wrong exchange. California runs Covered
California, and the CMS Marketplace API carries none of its plans:
`MARKETPLACE_STATES` is the 30 HealthCare.gov states.

The federal source that does cover California is CMS's **State-based Exchange
public use file** (<https://www.cms.gov/marketplace/resources/data/state-based-public-use-files>),
one zip per state and plan year. The 2026 file
(`californiasbpuf2026.zip`, labelled `05052026`, data dated 2026-06-03) was
profiled before any code was written; the numbers are in
[docs/findings/ca-sbe-puf.md](../findings/ca-sbe-puf.md).

- **Plans:** 190 individual on-exchange medical plans from 11 issuers, each with
  cost-sharing variants. Every bronze plan is "Expanded Bronze".
- **Premiums:** 28,101 filed monthly rates by plan, rating area (1–19) and age
  band (0-14, 15 to 63, 64 and over). There is no tobacco rating.
- **Service areas:** by issuer and service-area ID; 124 rows cover only some ZIPs
  of a county, and 5 cover the whole state.
- **Missing:** issuer names, and the SBC, brochure, formulary and network URLs.
  Those columns are empty on every row.
- **Rating areas:** not in the file. CMS publishes them separately, as a page
  (<https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra>).
  Counties map to one area each, except Los Angeles, which splits by 3-digit ZIP
  prefix.
- **Publication lag:** the file comes out months into its plan year: 2026 on
  2026-06-03, 2025 on 2025-05-06, 2024 on 2024-05-14. During open enrollment for
  next year (1 November to 31 January in California) only this year's data exists.

Covered California's own site is not an alternative. Its Terms of Use forbid
access "through any automated means (including, but not limited to, use of
scripts, web crawlers, or screen scrapers)" and republishing without a written
agreement.

## Decision

1. **A second, California-only loader** (`src/ingestion/ca_puf/`,
   `make ingest-ca-plans YEAR=`). It writes the existing `issuers`, `plans`,
   `plan_counties` and `plan_cost_shares`, plus three new tables:
   - `rating_areas`: county, or county and ZIP prefix, to rating area;
   - `plan_rates`: plan, area and age to a monthly rate;
   - `catalog_loads`: which file, which bytes (sha256), when.

   `plans.catalog_source` (`cms_api` or `ca_sbe_puf`) records which pipeline
   wrote each plan, so a source can be audited or removed. `MARKETPLACE_STATES`
   is unchanged. A generic loader for all 22 state-based exchanges was
   declined: each state still needs its own rating areas and issuer names.
2. **Premiums are filed rates, read in SQL.** The rate for the plan, the ZIP's
   rating area and the person's age, clamped to 14..64, is the premium. It is
   the same figure the live path shows: CMS's price for one person with no
   income, before any tax credit. CMS is never called for California;
   `age_rated_premiums` refuses a state it does not serve.
   `premium_reference` is NULL for California plans.
3. **A plan is sold only where it has a rate.** Western Health Advantage files
   one service area over rating areas 2 and 3, with a separate plan for each,
   each rated in one area. Taking the service area alone would offer each plan in
   counties it has no price for. So a service-area county is kept only where the
   plan is rated for that county's area; the 2026 file drops 40 of 1,239 pairs.
4. **The load is validated before any write, in one transaction.** A bad file
   changes nothing, and the previous load keeps serving. The load aborts when:
   - an issuer is unknown;
   - a county (other than Los Angeles) is missing from the map;
   - a service-area county is missing from the ZIP crosswalk;
   - a plan has no rates or is sold nowhere;
   - a plan is rated in an area where it is not sold.

   The last check is what catches a mistyped county in the hand-transcribed map.
   In the 2026 file, 156 of the 190 plans are rated in exactly one area.
5. **A ZIP with no rating area is shown unpriced, never guessed.** Four real Los
   Angeles ZIPs in CMS's 2026 crosswalk have a prefix in neither of the county's
   lists: 90134, 90140 and 90189 (901), and 93063 (930). Their plans are listed
   with "no filed rate", and the load reports them.
6. **Only in-network, individual cost shares are loaded,** for every
   cost-sharing variant. The search reads only these, and they are the only
   values whose API wording is verified. The variant labels in the PUF (`Limited
   Cost Sharing Plan Variation`, `94% AV Level Silver Plan`, …) are the API's.
7. **Say the year, and point to the exchange.** A search in California reports
   `premium_source = cms_filed_rates`, and `prior_year` when the plan year is
   before the year on sale (the next year from 1 November). The model then leads
   with "these are 2026 plans; 2027 plans aren't available here yet" and names
   Covered California. This stops by itself once the new file is loaded.
8. **Name the right exchange everywhere.** Tool results carry the exchange for
   the state. The prompts, the SBC "no link" reason and the frontend no longer
   send every state to HealthCare.gov. A Bronze filter now includes Expanded
   Bronze, in every state.

## Consequences

- California users compare real Covered California plans, with a premium for
  their age and ZIP, matching CMS's file to the cent. That was spot-checked
  against the raw rates.
- **California data lags every open enrollment by about six months.** This is
  said in every answer where it applies; it is not hidden.
- **Rating areas and issuer names are hand-transcribed.** They are re-checked
  every year ([docs/runbooks/california.md](../runbooks/california.md)), and the
  load's cross-checks fail loudly if they drift.
- **SBC documents are not loaded yet.** Every California plan shows "no Summary
  of Benefits link", because the PUF has none. Sub-project 2 of the California
  expansion builds a hand-reviewed list of links instead.
- **Quality ratings are not in the PUF.** California plans show "Not available",
  not "Not rated".
