# CMS Marketplace API — verified behavior

**Verified:** 2026-09-18, against a real key, state `TX`, ZIP `75001`
(Dallas County, FIPS `48113`).
**Referenced by:** [`docs/plans/phase-1-marketplace-api.md`](../plans/phase-1-marketplace-api.md)
(Steps 1–2), which this file supersedes as the source of truth for what the
live API actually does — the plan doc says what to build; this says what
was true when we checked.
**Re-verify before relying on this for:** any change to Step 2's real
ingestion pipeline, or if CMS's published documentation changes. Nothing
here is guaranteed to stay true — it is what was observed on the date
above, against one state and one county. Re-verifying is a handful of
`requests` calls, not a project.

## Why this file exists

Phase 1's plan (`docs/plans/phase-1-marketplace-api.md`) was originally
written entirely from CMS's published documentation — "designed from
documented capabilities, which is not the same thing" as a verified
response, in the plan's own words. A throwaway spike script
(`scripts/verify_marketplace_api.py`, since deleted per its own stated
purpose) was run against a real API key to close that gap. This file is
where its findings live on, separate from the roadmap document, so they
stay findable after Phase 1's status moves on.

## Auth and base URL

`https://marketplace.api.healthcare.gov/api/v1`, with `?apikey=` as a query
parameter on every call — matches the published docs, no surprises here.

## The catalog does not require a household

This was the fork question Step 1 was built to answer: can plan catalog
data (benefits, deductibles, metadata) be fetched per state/county
independently of rate quoting, or does every response require a household
context — which would force a live per-request design instead of a batch
one?

**Answer: no household is required.** `POST /plans/search` with the
`household` key omitted entirely still returns `200` with the full plan
list for the county — the same `total` (138 plans) as when a dummy
household was included. A household only changes two fields: `premium` and
`premium_w_credit`. Confirmed directly: the identical plan, identical
county, returned `premium: $323.30` for a 25-year-old and `premium:
$718.08` for a 55-year-old — real, substantial age-rating, roughly 2.2×.
Every other field — `benefits`, `deductibles`, `moops`, `issuer`,
`quality_rating`, all four document URLs — was identical regardless of
household.

**Consequence:** nightly batch ingestion is fully viable. A pipeline can
enumerate county → call `/plans/search` with no household (or one fixed
reference household) → store everything except premium as the catalog, and
treat premium as an indicative reference figure rather than a personalized
quote. That lines up with, rather than fights, Phase 1's separate decision
to exclude income/tobacco/household size from personalization — the two
were arrived at independently but turn out to be consistent.

## `place.countyfips` is required, not derivable from a ZIP alone

A request body with `{"state": "TX", "zipcode": "75001", "countyfips":
null}` is rejected: `400`, `"place: (countyfips: cannot be blank.)"`. The
county FIPS code has to be resolved first, via a separate call:

```
GET /counties/by/zip/75001?apikey=...&year=2026
→ {"counties":[{"zipcode":"75001","name":"Dallas County","fips":"48113","state":"TX"}]}
```

Confirmed working. A real ingestion pipeline needs to enumerate ZIP→county
(or county directly) per state — not just iterate the 30 states — before it
can call `/plans/search` at all. `GET /data/county-zips` is documented as a
bulk crosswalk endpoint and is the likely source for that mapping in one
shot, rather than one ZIP at a time; it was not called during this spike
and should be checked before Step 2's pipeline is built.

## Pagination: a fixed page size of 10

`/plans/search` always returns 10 plans per call, regardless of what
`limit` is set to — confirmed by sending `limit: 50` in the request body
and still receiving exactly 10 results. `offset` does work: `offset: 10`
returned a genuinely different first plan than `offset: 0`. The response
carries a `total` field (138 for this county) to page against.

Scale implication: Dallas County alone needed 14 requests (`⌈138/10⌉`) to
enumerate fully. Multiplied across every county in all 30 covered states,
full catalog ingestion is many thousands of requests — comfortably inside
the rate limit below, but the ingestion loop must page on `offset`
correctly and will likely need to de-duplicate plans that are shared across
multiple counties in the same rating area.

## Rate limits, from real response headers

Not published as a number anywhere on CMS's site — confirmed by reading
actual response headers on a live call:

```
RateLimit-Limit: 200            (per second)
X-RateLimit-Limit-second: 200
X-RateLimit-Limit-minute: 1000
RateLimit-Remaining, X-RateLimit-Remaining-second/-minute, RateLimit-Reset
  — all present and decrementing correctly across calls
```

Generous relative to the pagination volume above. A straightforward
sequential batch job does not need aggressive backoff to stay under this
limit. Even so, calls during and after this spike were deliberately paced
rather than run at the ceiling — courteous use of a free public API, and it
stays robust if CMS tightens the limit later without warning. Any future
ingestion pipeline or re-verification should keep that same discipline: a
small delay between calls, never a tight loop.

## Plan object — verified fields

Confirmed by calling both `POST /plans/search` (per-plan summary inside the
`plans` array) and `GET /plans/{id}` (single-plan detail, confirmed to need
**no** household context — `200` with just `?apikey=&year=`).

Top-level fields present on both:

```
id, name, premium, premium_w_credit, aptc_eligible_premium, ehb_premium,
pediatric_ehb_premium, metal_level, type, design_type,
is_standardized_plan, state, market, insurance_market, max_age_child,
service_area_id, product_division, simple_choice,
specialist_referral_required, waiting_period_duration,
covers_nonhyde_abortion, tobacco_lookback, guaranteed_rate,
suppression_state, is_ineligible, has_national_network, hsa_eligible,
rx_3mo_mail_order, benefits[], deductibles[], moops[], tiered_deductibles,
tiered_moops, disease_mgmt_programs[], quality_rating{}, issuer{}, sbcs{},
benefits_url, brochure_url, formulary_url, network_url
```

`GET /plans/{id}` additionally carries `pc_deductible_visits`, not present
in the `/plans/search` summary shape.

The separate `GET /issuers` endpoint (state-only, no household — confirmed
`200` for `TX` with just `?apikey=&year=&state=`) returns issuer records
with their own shape: `id, name, eligible_dependents[], address{}, state,
individual_url, shop_url, toll_free, tty`.

## Two corrections to the original design

### `benefits_url` is a real SBC PDF link — not "no documents"

The plan doc originally stated the API "does not return plan documents,
SBCs, or any contract language." That's wrong for one field.
`benefits_url` on a real plan checked during the spike was:

```
https://sbc.wellpoint.com/dpsdeeplink/deepLink/WellpointEssentialCatastrophicIncentives/8Y91/English/DG166708945620.pdf
```

— a direct link to the plan's actual Summary of Benefits and Coverage PDF,
not a landing page. `brochure_url`, `formulary_url` and `network_url` are
also real per-plan document/page links, confirmed present with non-empty
values.

This does **not** shrink the work in Phases 2–4 — downloading, parsing and
chunking SBC content is still out of scope for Phase 1 — but it means a
future SBC-ingestion phase can start from "fetch this known URL" instead of
"find this plan's SBC" some other way (e.g. scraping each issuer's site).
Worth capturing `benefits_url` as a plain column when Step 2's schema is
built, since it costs one field and no extra ingestion complexity — it's
already present in every plan response.

**Also found:** the field literally named `sbcs` on a plan object is *not*
a document link, despite the name. It holds the standardized
coverage-example cost estimates an SBC also displays as numbers — `baby`,
`diabetes`, `fracture` scenarios, each with `coinsurance`, `copay`,
`deductible`, `limit` — not a file. `benefits_url` is the actual document;
`sbcs` is same-named, different job.

### `deductibles` and `moops` are arrays, not scalars

The original schema sketch assumed four flat columns:
`deductible_individual`, `deductible_family`, `oop_max_individual`,
`oop_max_family`. The real shape is an array of objects on the plan:

```json
{
  "type": "Combined Medical and Drug EHB Deductible",
  "amount": 10600,
  "csr": "Exchange variant (no CSR)",
  "network_tier": "In-Network",
  "family_cost": "Individual",
  "individual": true,
  "family": false,
  "display_string": ""
}
```

— one entry per **CSR (cost-sharing reduction) variant**
(`"Exchange variant (no CSR)"`, plus the 73%/87%/94% silver-plan variants),
per network tier, and per individual-vs-family split. A single plan
carried more than four deductible rows in the spike response, and `moops`
follows the identical shape for out-of-pocket maximums. This needs a child
table (one row per plan × kind × variant × tier × family_cost), not scalar
columns on the plan row.

`issuer` and `quality_rating` are likewise nested objects, not plan-row
scalars — `issuer` carries the same shape `/issuers` returns directly
(`id, name, address, individual_url, shop_url, toll_free, tty`);
`quality_rating` carries four separate 0–5 sub-ratings
(`global/clinical/enrollee/efficiency`) each with its own
`*_not_rated_reason` — most plan year 2026 plans checked in the spike were
simply unrated (`"New-Ineligible for Scoring"`), so these need to be
nullable.

## Confirmed: `IL` is rejected, `TX` is accepted

Direct evidence for the "28 FFM + 2 SBM-FP = 30 states" coverage claim,
rather than trusting the documentation alone: calling `/plans/search` with
`state: "IL"` returns `400`,
`{"message":"state is not a valid marketplace state"}` — Illinois runs its
own state-based exchange and is no longer on the federal marketplace. The
identical request shape with `state: "TX"` returns real plan data. The
30-state boundary is enforced by the API server itself, not just
documented as a limitation.

## How this was gathered

`scripts/verify_marketplace_api.py` (a throwaway CLI, deleted once these
findings were written up — see its final form in git history at commit
`2e8da54` if it's ever useful as a starting point again) plus a handful of
follow-up ad hoc Python calls to resolve specific questions the first pass
raised (household-omission, age-sensitivity, `limit` vs. `offset`
behavior). All calls together numbered well under 25, against a rate limit
of 200/second — paced deliberately rather than run in a tight loop.
