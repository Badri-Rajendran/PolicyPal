# Phase 1 — Marketplace API catalog and plan comparison

**Status:** Step 1 (verification spike) complete; Step 2 not started
**Depends on:** [Phase 0](phase-0-hosted-llm.md) shipped green
**Blocks:** Phases 2–4 (SBC collection needs plan IDs and document URLs) — and
Step 1 found the API hands us candidate SBC URLs directly, see
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md)

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

Step 2's schema below is corrected for both. Whether to also add
`benefits_url` as a stored column (cheap, and sets up Phase 2) is flagged
there rather than decided silently.

## Step 2 — plan data is relational, not vector

New tables, entirely separate from `chunks`, carrying no embeddings.
Corrected against the verified shape in
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md)
— `deductibles`/`moops` are multi-row (per CSR variant, network tier,
individual/family), not scalar columns, and `issuer`/`quality_rating` are
nested objects:

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

Shaped by the verified findings (see the findings doc linked above): per
state, resolve counties (`/data/county-zips` or per-ZIP
`/counties/by/zip`), call `/plans/search` with no household per county, and
page on `offset` in steps of 10 until `offset >= total` — `limit` does not
change the page size. A small delay between calls, not a tight loop, even
though the 200/sec-1000/min limit would technically allow one.

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
