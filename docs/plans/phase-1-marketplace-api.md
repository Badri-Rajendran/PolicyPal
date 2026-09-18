# Phase 1 — Marketplace API catalog and plan comparison

**Status:** Steps 1–4 complete (API verified; catalog ingested; plan search in chat); Step 5 next
**Depends on:** [Phase 0](phase-0-hosted-llm.md) shipped green
**Blocks:** Phases 2–4 (SBC collection needs plan IDs and document URLs) — and
Step 1 found the API hands us candidate SBC URLs directly, see
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md)

## Goal

Ingest the CMS Marketplace API plan catalog, and let a user compare real
purchasable plans inside the chat transcript — "show me silver plans in
75801", "which of these has the lower deductible". (60601, the example this
line first used, is Chicago: Illinois runs its own exchange, and the API
rejects it.)

## Data source and its verified limits

[CMS Marketplace API](https://developer.cms.gov/marketplace-api). Keys are
granted to anyone who requests one, expire every 60 days, and auto-renew by
email.

Returns: premiums with and without APTC, deductibles, out-of-pocket maximums,
copays and coinsurance, essential health benefit detail, drug formulary
coverage, provider network inclusion, issuer details, quality star ratings,
and standard vs. non-standard plan design.

**Correction from the spike:** this line originally said the API "does not
return plan documents, SBCs, or any contract language." That's wrong for one
field — `benefits_url` is a direct link to the plan's real SBC PDF. Full
detail, including why this doesn't pull SBC parsing into this phase, is in
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md).

**Covers:** 27 FFM states + 3 SBM-FP (AR, OK, OR) = 30. ACA individual/family
only — 24.2M people. Not Medicare, Medicaid, or employer coverage. Verified
directly against the live API, not just documentation — see the findings
doc for the confirmed `IL`-rejected / `TX`-accepted example.

Scale for context: 183 QHP issuers on HealthCare.gov for plan year 2026.

## Step 1 — verification spike (complete)

Run via a throwaway script against a real key, state `TX`, ZIP `75001`
(Dallas County). Full findings, evidence, and exact field names are in
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md)
— this section is the summary that matters for what to build next.

**The open question (item 3) is answered: catalog data does NOT require a
household.** Only `premium`/`premium_w_credit` vary with household; every
other field — benefits, deductibles, moops, issuer, quality rating, document
URLs — is identical with or without one. **Nightly batch ingestion is fully
viable**: enumerate county → call the search endpoint with no household (or
one fixed reference household) → store everything except premium as the
catalog, treating premium as an indicative reference figure. That's
consistent with, not in tension with, the existing "Out of scope: subsidized
premiums, income, tobacco, household size" line below.

**`place.countyfips` is required and not derivable from state alone** —
needs a ZIP→county resolution step before the catalog can be queried at all.
A bulk county/ZIP crosswalk endpoint is documented but not yet verified;
check it before building Step 2's real pipeline.

**Pagination is a fixed page of 10; `limit` is ignored, `offset` works.**
One county alone had 138 plans (14 requests to enumerate). Full ingestion
across 30 states is many thousands of requests — comfortably inside the
verified rate limit (200/sec, 1000/min from real response headers), but call
politely (a small delay between calls), not at the ceiling.

**The two fields Step 2's original sketch got wrong, materially** (full
detail and exact response shapes in the findings doc):

- `deductibles` and `moops` are **arrays**, one row per CSR variant ×
  network tier × individual/family — not the four flat columns originally
  sketched. A silver plan alone has four CSR variants.
- `issuer` and `quality_rating` are **nested objects**, not plan-row
  scalars.

Step 2's schema below is corrected for both, and stores `benefits_url` too.

## Step 2 — plan data is relational, not vector (complete)

Four tables, entirely separate from `chunks`, carrying no embeddings. What
shipped, in `src/models/plan.py` and migration `faf714a14048` (ADR 0009):

```
issuers           hios_issuer_id + plan_year (unique), name, state,
                  individual_url, toll_free, tty

plans             hios_plan_id + plan_year (unique), issuer_id → issuers,
                  marketing_name, metal_level, plan_type, state,
                  premium_reference, hsa_eligible, has_national_network,
                  is_standardized_plan, four quality_rating_* sub-scores,
                  quality_not_rated_reason, benefits_url, brochure_url,
                  formulary_url, network_url

plan_counties     plan_id → plans, countyfips (unique together)

plan_cost_shares  plan_id → plans, kind ('deductible' | 'moop'),
                  cost_share_type, csr_variant, network_tier, family_cost
                  (all six unique together), amount
```

How it differs from what this section originally sketched, and why:

- **No `plan_benefits`.** Per-service cost sharing (the copay for a specific
  visit type) is ~50 benefit types × 3 tiers per plan, and nothing in Steps
  3–6 reads it. Deferred until a feature does.
- **`plan_counties` added.** Plans are sold per county. With only a state
  column, Step 4's `search_plans(zip_code, …)` could not narrow below the
  state and would return plans the caller cannot buy. The county is already
  known from the request that fetched each plan, so this costs no requests.
- **`cost_share_type` is in the cost-share unique key.** One real plan
  carries a $0 medical and a $5,500 drug deductible under an identical
  CSR/tier/family key. Without the type, one silently overwrites the other.
- **`premium_reference` is for a single 27-year-old**, sent explicitly on
  every call — CMS's own comparison convention. Omitting the household does
  not mean 27; CMS applies an undocumented default.
- **`benefits_url` is captured** — the SBC PDF, for Phase 2 to fetch
  directly. Storing a URL is not SBC parsing, which stays in Phase 2.
- **Quality ratings of `0` are stored as `NULL`.** CMS reports "not rated"
  as 0 on a 1–5 scale; kept as 0, every unrated plan ranks as worst.
- **Dropped as empty or redundant against real responses:** issuer address
  and `shop_url` (small-business market, out of scope); cost-share
  `display_string` (empty in every row checked) and `individual`/`family`
  (fully determined by `family_cost`).

Two reasons this does not go in pgvector:

- **Numbers do not embed.** "Deductible under $2,000" is a `WHERE` clause, not
  a similarity search. No embedding model gives useful ordering over currency
- **It keeps plan identity exact.** A plan row is retrieved by its key, never
  by approximate similarity, so there is no way to return Cigna's deductible
  for an Aetna question

The pipeline is `src/ingestion/plans.py` (orchestration and writes) over
`src/ingestion/marketplace_api.py` (the HTTP client), run as
`make ingest-plans STATES=TX,FL` or `STATES=ALL`. It is deliberately **not** a
`Source` subclass: that ABC produces chunks, and this produces rows.

- **Counties** come from one `/data/county-zips` call per run, cached per plan
  year in `data/plans/raw/` — the endpoint has taken 86 s to answer.
- **Paging** is on `offset` in steps of 10 until `offset >= total`; `limit`
  does not change the page size. Calls are paced at ~0.2 s, well under the
  verified 200/sec-1000/min limit.
- **Idempotent**: issuers and plans are upserted on their named unique
  constraints; cost shares are replaced per plan, so a variant dropped
  upstream does not linger. Verified by ingesting two TX counties twice —
  identical row counts and data fingerprints across all four tables.
- **Tolerant**: each county is one transaction. A county that fails is
  reported and skipped; the run continues.
- **The API key never reaches a log.** It travels as a query parameter, and
  `requests` embeds the full URL in both HTTP and connection errors, so every
  error is re-raised with method and path only.

**Known limits.** Plans are county-scoped and each county takes ~14 paged
requests, so one state is thousands of requests and `ALL` is tens of
thousands — hours at polite pacing. And an issuer may serve only part of a
county: searching with one representative ZIP per county can miss such a
plan, though it never records a plan the county does not sell.

## Step 3 — the `answer()` short-circuit (complete)

`answer()` returned `NO_ANSWER_RESPONSE` whenever retrieval found no chunks,
before any model call. "Show me silver plans in 75801" clears nothing against
the 0.5 relevance gate, so every plan question ended there. It is the same
shape as the failure [ADR 0005](../decisions/0005-conversation-history.md)
fixed: retrieval ran first and gave up before the later capability was
consulted.

What shipped ([ADR 0010](../decisions/0010-plan-search-tool.md)):

- **The free refusal remains when there is nothing to search.** With no
  chunks and an empty plan catalog, no model call is made.
- **Otherwise the model runs with the tool**, and a reply that drew on no
  chunk and no search is refused. The call is paid for, and nothing
  ungrounded is sent.
- **The regression is tested**: a plan question with an empty corpus result
  reaches the tool. Breaking the condition on purpose fails that test.

## Step 4 — the plan tool (complete)

Retrieval is unconditional and runs first, as sketched. There is one tool,
`search_plans`, offered whenever the catalog has rows. What shipped:

```
search_plans(zip_code, age, metal_level?, plan_type?, max_deductible?,
             county_fips?, sort_by?)
```

How it differs from the sketch, and why:

- **`county_fips` was added.** 28% of ZIPs span more than one county, and
  plans and prices are set per county. An ambiguous ZIP returns the county
  list for the model to ask about; merging the counties would list plans the
  user cannot buy.
- **`zip_counties` was added**, written by `make ingest-plans` from the
  county-zips payload it already downloads. It covers all 59 jurisdictions,
  so an out-of-marketplace ZIP is named as such.
- **Premiums are live for the user's age**, from `POST /plans`, verified in
  a third pass of the findings. They are sorted on the live figure: issuers'
  age factors differ, so the age-27 order does not hold. If CMS fails, the
  labelled age-27 premium is shown instead.
- **`sort_by` was added**, because only 10 plans come back and "lowest
  deductible" needs them ordered that way.
- **Catastrophic plans are left out from age 30** unless asked for.
- **The "form card when ZIP or age is missing" is `needs_input`.** The tool
  returns what is missing, and `Answer.needs_plan_inputs` carries it to
  Step 6.

Each plan fact is cited as `[Plan: <id>]` and each chunk as `[Source: …]`.

## Step 5 — API and persistence

`src/schemas/chat.py` — `MessageResponse` gains `plans:
list[PlanCardResponse] = []` alongside the existing `sources`.

New `message_plans` table mirroring `message_sources`, including **no foreign
key on `plan_id`** — the same reasoning as
[ADR 0007](../decisions/0007-persisting-citations.md): plan re-ingestion
replaces rows, and a cascade would delete conversation history.

Citations must survive a reload, exactly as sources do today.

## Step 6 — frontend

- `PlanCard` component rendered inside the transcript
- `ChatWindow` handles messages carrying `plans`
- A comparison is a table, so it needs its own `overflow-x: auto` container;
  the transcript itself must not scroll horizontally at phone width
- Follow `frontend/CLAUDE.md`: no boilerplate, no large comments or
  docstrings, readable and reviewable

## Tests and evals

Per CLAUDE.md, no feature is complete without tests and a passing CI run.

- **Component tests** for `PlanCard` and the form-card path — rendering,
  props/state, interaction, loading/empty/error states, accessibility
- **API tests** for every new endpoint — happy path, validation errors,
  authn/authz, boundaries, error responses, and throttling (429 with retry
  headers)
- **Ingestion tests** — idempotency, and the upsert key
- **Tool-selection floor** (done): a plan-search set in
  `scripts/eval_generation.py`, not `eval_retrieval.py`, because tool
  choice happens at generation. Definitional questions that search plans
  count as misses there.
- **A regression test for Step 3** (done): a plan question with an empty
  corpus result reaches the tool

## Security

- Marketplace API key in `.env`, never committed
- ZIP and age are the only personal inputs. **No income, tobacco, or household
  size** — so no subsidy calculation, and unsubsidized premiums are shown with
  a link to HealthCare.gov
- Keep ZIP and age out of logs
- Rate-limit the new endpoints; the upstream API has its own limits to respect
- Validate ZIP and age strictly — they reach an outbound HTTP call

## ADRs

- **0009** — plan data relational rather than vector
- **0010** — unconditional retrieval plus plan tools, per-fact provenance
  tagging, and the conditional `answer()` short-circuit it requires

## Verification

```bash
make ingest-plans          # then re-run: row count must not change
uv run pytest
uv run ruff check .
make ui-test && make ui-lint && make ui-build
```

End-to-end in the browser:

- a definitional question → prose with source citations
- "silver plans in 75801, I'm 34" → plan cards. **The regression test for
  Step 3** — it must reach the tool despite an empty corpus result
- "what's a deductible, and what's the cheapest silver deductible in 75801?"
  → one answer drawing on corpus chunks and plan rows together, each fact
  citing its own origin
- reload the thread → prose, citations and plan cards all persist
- a plan question with no ZIP → form card, not a guess

## Out of scope

- SBC ingestion — Phases 2–4
- Subsidized premiums, income, tobacco, household size
- Personalized recommendation — see the roadmap's rejected list
- State-based exchange plans (21 states + DC)
- Provider-network search, beyond what the plan row already carries
