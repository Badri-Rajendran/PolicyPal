# Phase 1 — Marketplace API catalog and plan comparison

**Status:** Step 1 (verification spike) complete; Step 2 not started
**Depends on:** [Phase 0](phase-0-hosted-llm.md) shipped green
**Blocks:** Phases 2–4 (SBC collection needs plan IDs and document URLs) — and
Step 1 found the API hands us candidate SBC URLs directly; see below

## Goal

Ingest the CMS Marketplace API plan catalog, and let a user compare real
purchasable plans inside the chat transcript — "show me silver plans in
60601", "which of these has the lower deductible".

## Data source and its verified limits

[CMS Marketplace API](https://developer.cms.gov/marketplace-api). Keys are
granted to anyone who requests one, expire every 60 days, and auto-renew by
email.

Returns: premiums with and without APTC, deductibles, out-of-pocket maximums,
copays and coinsurance, essential health benefit detail, drug formulary
coverage, provider network inclusion, issuer details, quality star ratings,
and standard vs. non-standard plan design.

**Correction from the spike:** this line originally said the API "does not
return plan documents, SBCs, or any contract language." That is wrong for
one field. `GET /plans/{id}` (and the plan objects inside `/plans/search`)
include `benefits_url`, and for a real plan checked during the spike it was
a direct link to the plan's actual Summary of Benefits and Coverage PDF —
not a landing page, the PDF itself
(`https://sbc.wellpoint.com/dpsdeeplink/deepLink/.../DG166708945620.pdf`).
`brochure_url`, `formulary_url` and `network_url` are also real document/page
links per plan. This does not shrink Phases 2–4's work — downloading,
parsing and chunking SBCs is still out of scope for Phase 1 — but it means
Phase 1 can capture the URL now, for free, as a plain column, and Phase 2 can
start from "fetch this known URL" instead of "find this plan's SBC." Whether
to capture it in Step 2's schema now is called out there.

Also found: the field named `sbcs` on a plan is **not** a document link. It
is the standardized coverage-example cost estimates (e.g. `baby`, `diabetes`,
`fracture` scenarios) that a printed SBC also carries, as numbers, not a
file — named the same, does a different job. `benefits_url` is the actual
document.

**Covers:** 28 FFM states + 2 SBM-FP (AR, OR) = 30. ACA individual/family
only — 24.2M people. Not Medicare, Medicaid, or employer coverage. Verified
directly: `IL` (no longer an FFM state — it runs its own exchange) returns
`{"message":"state is not a valid marketplace state"}` from `/plans/search`,
while `TX` returns real data. The 30-state boundary is enforced by the API
itself, not just documented.

Scale for context: 183 QHP issuers on HealthCare.gov for plan year 2026.

## Step 1 — verification spike (complete)

Run via `scripts/verify_marketplace_api.py` against a real key, state `TX`,
ZIP `75001` (Dallas County, FIPS `48113`). Findings below correct the
schema in Step 2.

**Auth & base URL.** `https://marketplace.api.healthcare.gov/api/v1`,
`?apikey=` query param on every call — matches the docs.

**The open question (item 3) is answered: catalog data does NOT require a
household.** `POST /plans/search` with `household` omitted entirely still
returns `200` with the full plan list for the county — same `total` (138)
as with a dummy household. A household only changes `premium` and
`premium_w_credit` (confirmed: age 25 → `$323.30`, age 55 → `$718.08`, same
plan, same county — real, large age-rating). Everything else — `benefits`,
`deductibles`, `moops`, `issuer`, `quality_rating`, the document URLs — is
identical regardless of household. **This means nightly batch ingestion is
fully viable**: enumerate county → call `/plans/search` with no household
(or one fixed reference household) → store everything except premium as the
catalog, and treat premium as an indicative reference figure, consistent
with the existing "Out of scope: subsidized premiums, income, tobacco,
household size" line below — that line was already the right call, and the
spike confirms it doesn't cost us catalog completeness.

**`place.countyfips` is required and not derivable from state alone.** A
bare `{"state": "TX", "zipcode": "75001", "countyfips": null}` fails with
`"place: (countyfips: cannot be blank.)"`. Resolve it first via
`GET /counties/by/zip/{zipcode}` (confirmed working, e.g. ZIP `75001` →
`{"fips": "48113", "name": "Dallas County", "state": "TX"}`). Real ingestion
needs to enumerate ZIP→county (or county directly) per state, not just
iterate states — `GET /data/county-zips` (documented, not yet called) is
the likely bulk source for that crosswalk rather than one ZIP at a time.

**Pagination: fixed page size of 10, `limit` is ignored, `offset` works.**
Confirmed: `limit: 50` in the request body still returned 10 results;
`offset: 10` returned a genuinely different first plan. Dallas County alone
had 138 plans — 14 requests to enumerate one county. Combined with 30
states' worth of counties, full ingestion is many thousands of requests,
which the rate limit (below) comfortably allows, but the ingestion loop
must page on `offset` correctly and probably de-duplicate plans shared
across counties in the same rating area.

**Rate limits, from real response headers — not documented as a number
anywhere on the site, exactly as suspected:**
`RateLimit-Limit: 200` (per second), `X-RateLimit-Limit-minute: 1000`.
Generous relative to the pagination volume above; a straightforward
sequential batch job does not need aggressive backoff to stay under it, but
should still request politely (a small delay between calls, not a tight
loop) rather than run at the ceiling — courteous API use, and it stays
robust if CMS tightens the limit later without warning.

**Plan object — real top-level fields** (`GET /plans/{id}`, no household
needed, confirmed `200`): `id, name, premium, premium_w_credit,
aptc_eligible_premium, ehb_premium, pediatric_ehb_premium, metal_level,
type, design_type, is_standardized_plan, state, market, insurance_market,
max_age_child, service_area_id, product_division, simple_choice,
specialist_referral_required, waiting_period_duration,
covers_nonhyde_abortion, tobacco_lookback, guaranteed_rate,
suppression_state, is_ineligible, has_national_network, hsa_eligible,
rx_3mo_mail_order, benefits[], deductibles[], moops[], tiered_deductibles,
tiered_moops, disease_mgmt_programs[], quality_rating{}, issuer{}, sbcs{},
benefits_url, brochure_url, formulary_url, network_url`. (`GET /plans/{id}`
additionally has `pc_deductible_visits` over the `/plans/search` shape.)

**The two fields Step 2's original sketch got wrong, materially:**

- **`deductibles` and `moops` are arrays, not scalars.** The draft schema
  had `deductible_individual`, `deductible_family`,
  `oop_max_individual`, `oop_max_family` as four flat columns. The real
  shape is a list of objects — `{type, amount, csr, network_tier,
  family_cost, individual, family, display_string}` — with one entry per
  **CSR variant** (`"Exchange variant (no CSR)"`, plus the 73%/87%/94%
  cost-sharing-reduction variants a silver plan actually has), per network
  tier, and per individual-vs-family. A single plan carried more than four
  deductible rows in the spike. This needs a child table shaped like
  `plan_benefits`, not four columns on `plans`.
- **`issuer` and `quality_rating` are nested objects, not plan-row
  strings/scalars.** `issuer` carries its own `id, name, address,
  individual_url, shop_url, toll_free, tty` — the same shape the
  `/issuers` endpoint returns directly. `quality_rating` carries four
  separate 0-5 sub-ratings plus a `*_not_rated_reason` per one (most 2026
  plans in the spike were simply unrated — `"New-Ineligible for Scoring"`).

Step 2's schema below is corrected for both. Whether to also add
`benefits_url` as a stored column (cheap, and sets up Phase 2) is flagged
there rather than decided silently.

## Step 2 — plan data is relational, not vector

New tables, entirely separate from `chunks`, carrying no embeddings.
Corrected against Step 1's verified shape — `deductibles`/`moops` are
multi-row (per CSR variant, network tier, individual/family), not scalar
columns, and `issuer`/`quality_rating` are nested objects:

```
issuers        issuer_id (HIOS), name, address, individual_url, shop_url,
               toll_free, tty

plans          plan_id (HIOS), plan_year, issuer_fk, marketing_name,
               metal_level, plan_type, state, premium_reference
               (the catalog premium from Step 1's no-household call —
               indicative, never a personalized quote; see Security below),
               hsa_eligible, has_national_network,
               quality_rating_global, quality_rating_clinical,
               quality_rating_enrollee, quality_rating_efficiency
               (nullable — most 2026 plans are simply unrated),
               benefits_url (flagged below, not yet decided)

plan_benefits  plan_fk, benefit_name, covered, copay, coinsurance, limits

plan_cost_shares  plan_fk, kind ("deductible" | "moop"), csr_variant,
                  network_tier, family_cost, individual, family, amount
```

`plan_cost_shares` is the schema correction: one row per
`(plan, kind, csr_variant, network_tier, family_cost)`, matching the array
the API actually returns instead of assuming one deductible per plan.

**Flagged, not decided here:** whether `plans.benefits_url` (the real SBC
PDF link Step 1 found) belongs in this phase's schema. Capturing it costs
one column and no extra ingestion complexity — it's already in every plan
response. Storing it does not pull SBC *download or parsing* into this
phase; that stays Phase 2's job per "Out of scope" below. Recommend
capturing it now since it's free and de-risks Phase 2, but flagging rather
than deciding unilaterally, since it does touch the Phase 1/2 boundary the
roadmap deliberately drew.

Unique on `(plan_id, plan_year)`. Idempotent upsert, so a re-run changes no
row count.

Two reasons this does not go in pgvector:

- **Numbers do not embed.** "Deductible under $2,000" is a `WHERE` clause, not
  a similarity search. No embedding model gives useful ordering over currency
- **It keeps plan identity exact.** A plan row is retrieved by its key, never
  by approximate similarity, so there is no way to return Cigna's deductible
  for an Aetna question

Follow the existing model conventions in `src/models/` — SQLAlchemy 2.0
`Mapped` / `mapped_column`, as in `src/models/chunk.py`.

New pipeline `src/ingestion/plans.py` plus a `make ingest-plans` target. It is
deliberately **not** a `Source` subclass: that ABC in
`src/ingestion/sources/base.py` produces chunks, and this produces rows. Do not
force it into an interface that does not fit.

Shaped by Step 1's findings: per state, resolve counties (`/data/county-zips`
or per-ZIP `/counties/by/zip`), call `/plans/search` with no household per
county, and page on `offset` in steps of 10 until `offset >= total` — `limit`
does not change the page size. A small delay between calls, not a tight
loop, even though the 200/sec-1000/min limit would technically allow one.

## Step 3 — fix the `answer()` short-circuit first

`src/services/generation.py:191`:

```python
if not chunks:
    return NO_ANSWER_RESPONSE
```

The model is never called — `test_fallback_does_not_load_the_model` asserts it.

**This breaks every plan question under the target flow.** "Show me silver
plans in 60601" clears nothing against the 0.5 relevance gate on a
Wikipedia/HealthCare.gov corpus, so `chunks == []`, so the user gets "I
couldn't find an answer" and the plan tool is never reached.

This is structurally identical to the failure
[ADR 0005](../decisions/0005-conversation-history.md) already fixed once:
retrieval runs first and short-circuits before the later capability is
consulted. Recognising it early is the point of writing it down here.

The early exit becomes conditional on there being no chunks **and** no plan
data available — while still avoiding a paid API call when genuinely nothing
can be answered.

## Step 4 — retrieval flow and the plan tool

Retrieval is unconditional. It runs before the model on every prompt:

```
user prompt
  → RAG retrieves chunks (local embeddings + rerank)
  → chunks go into the LLM context
  → LLM also has plan tools available
  → LLM answers from both together
```

So there is **one** tool, not two. `search_corpus` is not a choice the model
makes, because `search()` has already run.

`src/services/tools.py`:

```
search_plans(zip_code, age, metal_level?, plan_type?, max_deductible?)
```

Corpus chunks and plan rows share one context. Tag each context item with its
source type and identifier so a citation resolves back to whatever produced
it — a design goal for citation accuracy, not a restriction on merging.

When ZIP or age is missing, return a form card rather than guessing at them.

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
- **Tool-selection accuracy floor**, the natural sibling to the existing
  routing and coverage floors in `scripts/eval_retrieval.py`
- **A regression test for Step 3**: a plan question with an empty corpus
  result must still reach the tool

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
- "silver plans in 60601, I'm 34" → plan cards. **The regression test for
  Step 3** — it must reach the tool despite an empty corpus result
- "what's a deductible, and what's the cheapest silver deductible in 60601?"
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
