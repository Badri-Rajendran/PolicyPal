# Phase 1 — Marketplace API catalog and plan comparison

**Status:** not started
**Depends on:** [Phase 0](phase-0-hosted-llm.md) shipped green
**Blocks:** Phases 2–4 (SBC collection needs plan IDs and document URLs)

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

**Does not return:** plan documents, SBCs, or any contract language.

**Covers:** 28 FFM states + 2 SBM-FP (AR, OR) = 30. ACA individual/family
only — 24.2M people. Not Medicare, Medicaid, or employer coverage.

Scale for context: 183 QHP issuers on HealthCare.gov for plan year 2026.

## Step 1 — verification spike, before any schema work

**The live request/response shape has not been verified against a real key.**
Everything below is designed from documented capabilities, which is not the
same thing. Do this first and let the findings correct the schema:

1. Request a key at [developer.cms.gov/marketplace-api/key-request.html](https://developer.cms.gov/marketplace-api/key-request.html)
2. Call the plan-search and issuer endpoints; record actual field names,
   types, nullability, and pagination behaviour
3. **Answer the open question:** can plan catalog data (benefits, deductibles,
   plan metadata) be fetched per state independently of rate quoting, or does
   every response require a household context? This decides whether ingestion
   is a nightly batch or a live per-request call with aggressive caching —
   a fork that changes the whole pipeline design
4. Record rate limits and whether they permit bulk ingestion at all

Write the findings into this document before continuing. The spike is throwaway
code; nothing from it is kept.

## Step 2 — plan data is relational, not vector

New tables, entirely separate from `chunks`, carrying no embeddings:

```
plans          plan_id (HIOS), plan_year, issuer_name, marketing_name,
               metal_level, plan_type, state, premium_base,
               deductible_individual, deductible_family,
               oop_max_individual, oop_max_family, quality_rating

plan_benefits  plan_fk, benefit_name, covered, copay, coinsurance, limits
```

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
