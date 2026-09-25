# California plan comparison, and a source registry — design

**Status:** proposed · **Date:** 2026-09-24 · **Sub-project:** 1 of 5 in the California expansion
(SP0 + SP1). Later sub-projects are SBC documents, SBC hybrid search, California rules and rights,
and a provider-directory spike. Each gets its own spec.

## Why

A signed-up user with a California ZIP gets `not_marketplace_state`, and the model tells them to
go to HealthCare.gov (`src/services/generation.py:76-77`). That is the wrong exchange. California
runs Covered California, and the CMS Marketplace API has none of its plans.

This change makes plan comparison work for California: the same cited, compare-never-recommend
table the 30 HealthCare.gov states get. It also starts a committed source registry. The expansion
is a pilot today and may become commercial, so every data source needs a recorded license and
permission status, and a way to be removed.

## Scope

**In:**
- ACA individual and family plans sold on Covered California, plan year 2026.
- Premiums by age, deductibles and out-of-pocket maximums, filtered by county and ZIP.
- The exchange named correctly wherever the app names one.
- A source registry covering the existing sources and the new ones.

**Out, each for a later sub-project:**
- SBC documents and plan coverage answers (SP2).
- Cross-plan coverage search (SP3).
- California rules and rights content (SP4).
- Provider networks (SP5).
- Off-exchange and small-group (SHOP) plans.
- Dental plans.
- Subsidy estimates: the app shows the full, pre-subsidy price, as it does today.
- Other states that run their own exchanges. The loader is California-only by decision.

## The data, as verified

**Plans come from the CMS State-based Exchange public use file (PUF)**
- Source: `https://www.cms.gov/files/zip/californiasbpuf2026.zip`, a federal work in the public domain.
- It was downloaded and profiled on 2026-09-24. The file is labelled `05052026`, and CMS dates the
  data 2026-06-03.

Individual, on-exchange, medical-only plans:

| Item | Value |
| --- | --- |
| Plan IDs | 663: 190 base plans (`STANDARD COMPONENT ID`), each with CSR variants |
| CSR variant suffix | `-01` standard, `-02` zero cost sharing, `-03` limited cost sharing, `-04`/`-05`/`-06` Silver 73/87/94 |
| Issuers | 11. `ISSUER NAME` is blank on every row |
| Metal levels | Silver, Gold, Platinum, **Expanded Bronze**, Catastrophic. No plain "Bronze" |
| Rates | age `0-14`, 15–63, `64 and over` × `Rating Area 1`–`19`; tobacco `No Preference` |
| Service areas | keyed by **(issuer, service area ID)**, since IDs such as `CAS001` repeat across issuers. 124 partial-county rows list ZIPs; 5 statewide rows have a blank county |
| Link columns | SBC, brochure, formulary and network URLs are **empty on every row** |
| Money text | `"$5,200 "`, `"Not Applicable"`, `""`, `"$10600 per person \| $21200 per group"` |
| Integrated MOOP | `MEDICAL DRUG MAXIMUM OUT OF POCKET INTEGRATED` is `Yes` on every row, so only the TEHB MOOP columns carry values |

The rates file also covers dental and small-group plans, so the loader filters by the plan IDs it
kept.

**Issuer names.** The file doesn't give them. They are curated and were checked against each
issuer's service-area footprint:

| HIOS issuer ID | Carrier |
| --- | --- |
| 27603 | Anthem Blue Cross |
| 70285 | Blue Shield of California |
| 47579 | Balance by CCHP (San Francisco, San Mateo) |
| 67138 | Health Net |
| 51396 | Inland Empire Health Plan (Riverside, San Bernardino) |
| 40513 | Kaiser Permanente |
| 92815 | L.A. Care Health Plan (Los Angeles) |
| 18126 | Molina Healthcare |
| 92499 | Sharp Health Plan (San Diego) |
| 84014 | Valley Health Plan (Santa Clara) |
| 93689 | Western Health Advantage |

These match the 11 carriers Covered California announced for 2026, after Aetna's exit. Before
merging, cross-check the names against a federal issuer list, such as the CMS rate-review or MLR
public use files.

**Rating areas** come from CMS, "California Geographic Rating Areas"
(`https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra`), read
from the raw page.
- All 58 counties map to areas 1–14 and 17–19.
- Los Angeles County splits by 3-digit ZIP:
  - area 15: 906, 907, 908, 910, 911, 912, 915, 917, 918, 935
  - area 16: 900, 902, 903, 904, 905, 913, 914, 916, 923, 928, 932
- 909 appears in neither list. A Los Angeles ZIP whose prefix is unlisted is an error, never a guess.

**Publication lag.** CMS publishes each year's SBE PUF months into that year: 2026 on 2026-06-03,
2025 on 2025-05-06, 2024 on 2024-05-14. During 2027 open enrollment (2026-11-01 to 2027-01-31) only
2026 California data exists.

## Decisions

1. **A second catalog pipeline, not a generic one.** A California-only loader writes into the
   existing plan tables. `MARKETPLACE_STATES` stays exactly as it is, and the 30-state API path is
   untouched. California joins as a *filed-rate* state: its prices are stored, not fetched live.
2. **Prices come from filed rates, in SQL.**
   - The premium for a person is the PUF rate for their plan, rating area and age band.
   - This is the same figure the live path shows: CMS's `POST /plans` with a single-person household
     and no income returns the full, pre-subsidy price.
   - `premium_reference` stays NULL for California, so a missing rate means unpriced, never free
     (ADR 0010).
3. **Label the year and degrade (user decision).**
   - Show the newest California year loaded, labelled with its plan year.
   - When that year is before the plan year on sale (the next year from 1 November), the answer
     leads with: these are {year} plans and prices; {year on sale} plans are not available here
     yet; see Covered California.
   - When CMS publishes the new file and it is loaded, this switches off with no code change.
4. **Covered California is linked, never read.** Its Terms of Use forbid automated access and
   republishing without a written agreement. The app names it and links to it; nothing fetches it.
5. **A committed source registry**, before any new source is used (user decision: commercial
   later).
6. **Fix the Bronze filter for every state.** A `Bronze` filter currently matches only `Bronze`
   (`src/services/plan_search.py:201-202`), so every California bronze plan, and every Expanded
   Bronze plan in the API states, is missed. `Bronze` now matches both.

## Design

### SP0 — source registry and exchanges

**`src/ingestion/sources/registry.toml`** is committed and read with the standard library's
`tomllib`, so there is no new dependency. There is one `[[source]]` table per source:

| Field | Values |
| --- | --- |
| `id` | stable key, e.g. `cms_ca_sbe_puf` |
| `name`, `publisher`, `scope_urls` | descriptive |
| `kind` | `corpus` · `catalog` · `sbc_host` · `directory` |
| `jurisdiction` | `US` or a state code |
| `license`, `license_url` | as published |
| `permission_status` | `public_domain` · `open_license` · `written_permission` · `pending_review` · `denied` |
| `commercial_use` | `yes` · `no` · `review` |
| `robots`, `robots_checked_on` | `allowed` · `disallowed` · `unavailable` · `not_applicable` |
| `access` | `api` · `download` · `crawl` · `manual` |
| `verified_on` | ISO date |
| `enabled` | bool; only `public_domain`, `open_license` or `written_permission` may be `true` |
| `removal` | how to take this source out |
| `notes` | free text |

Entries in this change:

| id | Enabled |
| --- | --- |
| `wikipedia` | yes |
| `healthcare_gov` | yes |
| `cms_marketplace_api` | yes |
| `cms_ca_sbe_puf` | yes |
| `cms_ca_rating_areas` | yes |
| `coveredca` | **no**: `denied`, link only, with the Terms of Use clause cited |

The CA carrier SBC hosts, CDI and DMHC are recorded in the sub-projects that would use them.

**`src/ingestion/sources/registry.py`**
- `load_registry()`
- `require_enabled(source_id)` raises `SourceNotApprovedError`
- `validate()` checks required fields, the allowed values, and that no enabled entry has an
  unapproved permission status.

`Source` (`src/ingestion/sources/base.py`) gains a `registry_id`. The corpus pipeline and the new
loader call `require_enabled` before fetching. A test asserts that every `Source` in
`src/ingestion/sources/__init__.py` has an entry.

**`src/core/exchanges.py`** (in core, because ingestion and services both use it):

```python
@dataclass(frozen=True)
class Exchange:
    name: str
    url: str

HEALTHCARE_GOV = Exchange("HealthCare.gov", "https://www.healthcare.gov/")
FILED_RATE_STATES = {"CA": Exchange("Covered California", "https://www.coveredca.com/")}
CATALOG_STATES = MARKETPLACE_STATES + tuple(FILED_RATE_STATES)

def exchange_for(state) -> Exchange | None: ...  # HealthCare.gov for API states, CA's own, else None
```

**`src/core/plan_year.py`**: `plan_year_on_sale(on: date) -> int` returns `on.year + 1` from
1 November, otherwise `on.year`.

### SP1 — schema

One Alembic migration after head `f6e50c4aec26`:

| Change | Type | Notes |
| --- | --- | --- |
| `plans.catalog_source` | `String(16)` NOT NULL, server default `'cms_api'` | California rows get `'ca_sbe_puf'`. Makes a source auditable and removable |
| `plan_counties.zipcodes` | `ARRAY(String(5))`, nullable | NULL means the whole county. That is what the API path writes, so it is unaffected |
| `rating_areas` (new) | `id`, `state`, `plan_year`, `countyfips`, `zip3 String(3)` NOT NULL default `''`, `rating_area SmallInteger` | Unique `(plan_year, countyfips, zip3)`. `''` means the whole county: not NULL, because NULLs are distinct in a unique key (see `PlanCostShare`) |
| `plan_rates` (new) | `id`, `plan_id` FK → `plans.id` ON DELETE CASCADE, `rating_area SmallInteger`, `age SmallInteger`, `individual_rate Numeric(10,2)` | Unique `(plan_id, rating_area, age)`. `age` 14 stands for the 0–14 band, 64 for 64 and over |
| `catalog_loads` (new) | `id`, `source`, `state`, `plan_year`, `file_url`, `file_label`, `sha256`, `plans`, `loaded_at` | One row per load. The data-freshness label comes from here |

The models go in `src/models/plan.py`. `alembic check` must stay clean.

### SP1 — loader: `src/ingestion/ca_puf/`

| Module | Job |
| --- | --- |
| `download.py` | Fetches the zip to `data/plans/raw/ca_puf/{year}.zip` (gitignored), written aside and renamed, as in `src/ingestion/marketplace_api.py:41-67`. Uses `USER_AGENT` from `src/ingestion/constants.py`. HTTP 404 means "not published yet", exit code 3. `--zip PATH` takes a file downloaded by hand |
| `read.py` | Pure functions from the zip to row dicts. No database, so it is fully unit-testable |
| `issuers.py` | `CA_ISSUERS`, the table above, with its source and verified date. An unknown issuer ID raises |
| `rating_areas.py` | The county → area map and the Los Angeles ZIP3 split, with the CMS URL and verified date |
| `load.py` | Writes one state-year in one transaction |
| `__main__.py` | `python -m src.ingestion.ca_puf --year 2026 [--zip PATH]` |

**Reading (`read.py`)**
- CSVs are read with `csv.DictReader` and `utf-8-sig`.
- Rows kept: `MARKET COVERAGE=Individual`, `DENTAL ONLY PLAN=No`, `QHP NONQHP TYPE ID=On the
  Exchange`, and a plan ID suffix other than `-00`.
- **Plan rows** use the base plan ID from `STANDARD COMPONENT ID`. The other fields come from the
  `-01` row:
  - `marketing_name` = `PLAN MARKETING NAME`
  - `plan_type` = `PLAN TYPE`
  - `metal_level` verbatim, so `Expanded Bronze` stays as CMS writes it (ADR 0009)
  - `hsa_eligible` and `has_national_network` from Yes/No
  - `state` = `CA`, `catalog_source` = `ca_sbe_puf`
  - `is_standardized_plan`, the quality ratings, `premium_reference` and the four URL fields are
    `None`
- **Cost shares** give one `plan_cost_shares` row per non-empty value.

  The search reads only the combination no CSR, `In-Network`, `Individual` (`_cost_shares()`,
  `src/services/plan_search.py:161-185`). Those rows must use exactly the strings the API path
  writes, which are verified in `docs/findings/cms-marketplace-api.md`:

  | PUF columns (INN TIER 1, individual) | `kind` | `cost_share_type` |
  | --- | --- | --- |
  | `TEHB DED INN TIER 1 INDIVIDUAL` | deductible | `Combined Medical and Drug EHB Deductible` |
  | `MEHB DED INN TIER1 INDIVIDUAL` | deductible | `Medical EHB Deductible` |
  | `DEHB DED INN TIER1 INDIVIDUAL` | deductible | `Drug EHB Deductible` |
  | `TEHB INN TIER 1 INDIVIDUAL MOOP` | moop | `Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)` |

  - Suffix `-01` maps to `csr_variant = "Exchange variant (no CSR)"`, `network_tier = "In-Network"`,
    `family_cost = "Individual"`.
  - The other CSR variants, tiers and family splits are stored too, labelled with the PUF's own
    words (`CSR VARIATION TYPE`, `In-Network (Tier 2)`, `Out-of-Network`, `Family Per Person`,
    `Family Per Group`). The search doesn't read them. The findings doc will say they are PUF
    vocabulary, not API vocabulary.
- **Money parsing** is its own `_puf_money()`: it trims, drops `$` and `,`, and returns None for
  `""` and `Not Applicable`. For `per person | per group` it takes each part in turn.
  `plans._money` expects numbers, so it can't be reused.
- **Service areas** are joined on (`ISSUER ID`, `SERVICE AREA ID`).
  - The county FIPS is the part of `COUNTY` after ` - `.
  - A partial county becomes a sorted list of its ZIPs.
  - Duplicate plan-county pairs are merged, and a whole-county row wins over a partial one.
  - `COVER ENTIRE STATE=true` expands to every California county in `zip_counties`.
- **Rates** are keyed by (base plan ID, area number, age key), from `INDIVIDUAL RATE`.

**Loading (`load.py`)**
1. Require `zip_counties` rows for the year. If there are none, write them by reusing
   `county_zips(year)` and `_write_zip_counties` (`src/ingestion/plans.py:198`). That needs the CMS
   key; without it, stop and say to run `make ingest-plans` first.
2. **Validate before writing.** Abort with nothing written if any of these hold:
   - a Los Angeles ZIP3 in `zip_counties` is unmapped;
   - a California county is missing from the crosswalk;
   - an issuer is unknown;
   - any plan-county has no rate in its mapped rating area. 156 of the 190 plans are rated in
     exactly one area, so a mistranscribed county fails here.
3. Upsert issuers and plans with `plans.upsert` (`src/ingestion/plans.py:141`).
4. Replace the California plans' counties, cost shares and rates for the year, and delete
   California plans for the year that are no longer in the file. The file is authoritative.
5. Replace `rating_areas` for the year, and insert a `catalog_loads` row with the zip's sha256.

The whole load is one transaction: a failure leaves the previous load intact.

**CLI:** `make ingest-ca-plans YEAR=2026 [ZIP=path]`. `resolve_states` (`src/ingestion/plans.py:43`)
keeps `make ingest-plans` limited to the 30 API states. Its error for `CA` names
`make ingest-ca-plans`.

### SP1 — search (`src/services/plan_search.py`)

- **Where a ZIP is served.** Split out `_resolve_place(session, zip_code, county_fips)` from
  `search_plans` (lines 271-293); SP3 will reuse it. A county is served when its state is in
  `MARKETPLACE_STATES`, or is in `FILED_RATE_STATES` **and** has plans loaded. Before any California
  load, a California ZIP still gets `not_marketplace_state`, now carrying the Covered California
  exchange.
- **The year.** `_counties_for_zip` already picks the newest year in which the ZIP's own county has
  plans (lines 128-148). A California ZIP stays on 2026 after federal 2027 data loads, with no change
  needed.
- **ZIP-aware service areas.** The loaded-county check and `find_plans` add
  `PlanCounty.zipcodes IS NULL OR :zip = ANY(PlanCounty.zipcodes)`. `find_plans` gains a
  `zip_code` argument.
- **Bronze.** A `Bronze` filter becomes `metal_level IN ('Bronze', 'Expanded Bronze')`. An
  `Expanded Bronze` filter stays exact.
- **Filed-rate pricing**, when the county's state is in `FILED_RATE_STATES`:
  - `_rating_area(session, year, countyfips, zip_code)` takes the ZIP3 row, otherwise the
    whole-county row.
  - `rate_age(age) = min(max(age, 14), 64)`.
  - `find_plans` outer-joins `plan_rates` on (plan, area, age), orders by that rate when sorting by
    premium, and fills in `monthly_premium` and `premium_age`.
  - `_price` is not called.
  - `age_rated_premiums` raises `ValueError`, before any HTTP request, for a state outside
    `MARKETPLACE_STATES`: defence in depth.
- **Catastrophic plans:** the existing age rule (line 295) applies unchanged.
- **`PlanSearchResult`** gains:
  - `exchange`: an `Exchange` or None;
  - `premium_source`: `cms_live` or `cms_filed_rates`;
  - `plan_year_on_sale`;
  - `prior_year`: `plan_year < plan_year_on_sale(profile.today())`, only for filed-rate states.

### SP1 — tools, prompts, profile, frontend

**Tools and prompts**
- `tools._render` (`src/services/tools.py:189`) adds `exchange` (name and URL), `premium_source`,
  `prior_year` and `plan_year_on_sale`. `not_marketplace_state` carries `exchange` when one is known.
- `generation.PLAN_TOOL_PROMPT`:
  - `not_marketplace_state` points to the exchange named in the result, or "the state's own
    exchange" when none is named. HealthCare.gov is never hard-coded.
  - For `cms_filed_rates`: the premium is CMS's published {plan_year} rate for that plan and age,
    before any federal tax credit or California premium help.
  - For `prior_year`: lead with "These are {plan_year} plans and prices; {plan_year_on_sale} plans
    aren't available here yet", then point to the exchange.
- `COVERAGE_PROMPT` (line 131) and `sbc_status.REASONS["no_link"]` stop naming HealthCare.gov. Until
  SP2, every California plan is `no_link`, and the wording must hold for it.

**Profile.** `src/services/profile.py`:
- `is_marketplace_state` becomes `plan_search_available(state)`, meaning in `CATALOG_STATES`.
- `ProfileResponse` and `CountiesResponse` (`src/schemas/profile.py`) gain `exchange_name` and
  `exchange_url`.
- `marketplace_state` keeps its name, for compatibility, but now means "plan comparison available".
- No new endpoints.

**Frontend**
- `frontend/src/features/plans/exchanges.js` maps a state to its exchange name and URL.
- `PlanComparison.jsx`:
  - the caption says "{plan_year} plans";
  - the footnote links the right exchange, and for California says the premiums are CMS's published
    rates before any tax credit or state help;
  - the quality column shows "Not available" for California instead of "Not rated".
- `ProfileFields.jsx` names Covered California for a California county.

## Error handling

| Case | Behaviour |
| --- | --- |
| PUF not yet published (404) | Exit code 3 with a message; nothing written |
| PUF columns renamed or missing | `read.py` raises naming the column, before any write |
| Validation failure (unmapped ZIP3, unknown issuer, missing rate) | The transaction is not started; the previous load stays |
| California ZIP, nothing loaded | `not_marketplace_state` with Covered California |
| Rate missing for a plan, area or age at query time | Unpriced, never free, and never a guessed price |
| Live CMS call attempted for California | Raises before HTTP; caught as today, so the plan shows unpriced |

## Security

- Parameterized SQLAlchemy only.
- The ZIP and age are used in SQL filters, never logged. The existing log lines stay as they are.
- The download goes over HTTPS to a fixed CMS host.
- No PUF file is committed; `data/` stays gitignored.
- No new endpoints. The payload of `/api/profile` and `/api/counties` grows by two public fields; its
  authentication and rate limits are unchanged, and re-tested.

## Testing

**Pytest**
- `tests/test_ca_puf_read.py`, using small synthetic CSVs in `tests/fixtures/ca_puf/`, made up and
  not copied from the real file:
  - money formats;
  - suffix → variant;
  - the four row filters;
  - Expanded Bronze kept;
  - an unknown issuer raises;
  - the service-area join on the issuer pair;
  - statewide expansion and partial ZIP lists;
  - age keys;
  - the Los Angeles split, with 909 raising.
- `tests/test_ca_puf_load.py`, against the database:
  - loading twice gives the same counts;
  - a plan dropped from the file is deleted;
  - `catalog_loads` is written;
  - Texas plans are untouched;
  - a rating-area mismatch aborts with nothing written.
- `tests/test_plan_search.py`:
  - California prices from `plan_rates` with no CMS call;
  - Los Angeles areas 15 and 16;
  - a ZIP outside a partial county;
  - ages 10 and 70;
  - `prior_year` with today patched to 2026-11-15, and false once a 2027 load exists;
  - an unloaded California ZIP gets Covered California;
  - `Bronze` matches Expanded Bronze;
  - catastrophic plans excluded at 30;
  - the Texas path unchanged.
- `tests/test_marketplace_api.py`: California raises without HTTP.
- `tests/test_tools.py` and `tests/test_generation.py`: the new fields render, and there is no
  unconditional HealthCare.gov.
- `tests/test_profile_api.py`: California available with its exchange; New York unavailable with
  none; the `/api/profile` and `/api/counties` 429 limits re-asserted.
- `tests/test_registry.py`:
  - every `Source` is registered;
  - only approved entries are enabled;
  - required fields are present;
  - `coveredca` is disabled.

**Vitest:** `PlanComparison`, `ProfileFields`, `useProfileFields` and `exchanges`, covering rendering,
the California and Texas footnotes, the year caption, "Not available", and accessibility names on
the new links.

**Playwright** (the plugin, run against the local stack):
1. Sign up with ZIP 90012.
2. The profile names Covered California.
3. "Compare silver plans" returns a table with a 2026 caption, the filed-rate footnote and the
   Covered California link.

**Eval:** add California cases to `scripts/eval_generation.py` `run_plan_searches`: a Los Angeles
Silver request and a Bronze request. They check that Covered California is named and HealthCare.gov
is not.

**CI:** `make check`, which runs lint, tests with coverage ≥85%, and `alembic check`.

## Documentation

- **ADR 0024**, California plans from the SBE PUF. It amends ADR 0009 (a second catalog pipeline;
  `premium_reference` NULL for California) and ADR 0010 (California prices come from filed rates in
  SQL).
- **ADR 0025**, a committed source registry.
- `docs/findings/ca-sbe-puf.md`: the profile of the data above, and the cost-share vocabulary
  caveat.
- `docs/runbooks/california.md`, the yearly routine:
  1. From May to August, watch for the next year's PUF.
  2. Re-verify the rating-area page and the issuer list.
  3. Run `make ingest-ca-plans YEAR=`.
  4. Dump and restore to Azure (`docs/runbooks/deploy.md` step 5).
- README: scope now includes Covered California plans. CHANGELOG entries for each commit.

## Delivery

Two PRs from `feature_ca_plan_catalog`, or a stacked second branch:

1. **SP0:** the registry, exchanges, plan year on sale, the Bronze fix and the HealthCare.gov
   wording fix. This is useful on its own and changes no data.
2. **SP1:** the migration, loader, filed-rate search, profile and frontend, and data loaded locally.
   Before merging, the evidence:
   - 190 plans;
   - 11 issuers;
   - every California plan-county has a rate;
   - the Playwright run.

After merging, seed Azure per the deploy runbook.

## Open items

- Cross-check the curated issuer names against a federal issuer list (a pre-merge task, SP1).
- Blue Shield publishes a rating-region page (`blueshieldca.com/regions`) that could serve as a
  second check of the county map. It is used only as a check, never as a source.
