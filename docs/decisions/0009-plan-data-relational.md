# 0009 — Plan catalog data is relational, not vector

## Status

Accepted

## Context

Phase 1 lets a user compare real purchasable health plans — "silver plans in
60601", "which has the lower deductible". The data comes from the CMS
Marketplace API, whose verified behaviour is recorded in
[`docs/findings/cms-marketplace-api.md`](../findings/cms-marketplace-api.md).

Everything PolicyPal stored until now went into pgvector as corpus chunks,
retrieved by similarity. Plan data does not fit that shape. The questions
users ask about plans are comparisons over numbers, and a plan has to be
identified exactly: showing one issuer's deductible in answer to a question
about another's is a wrong answer about a real purchase.

## Decision

Plan data lives in four relational tables with no embeddings — `issuers`,
`plans`, `plan_counties` and `plan_cost_shares` — loaded by a separate
pipeline, `make ingest-plans STATES=…`, and never by `make ingest`.

- **Numbers do not embed.** "Deductible under $2,000" is a `WHERE` clause.
  No embedding model orders currency usefully.
- **Identity must be exact.** A plan row is fetched by its key, never by
  approximate similarity.
- **Separate pipeline, separate key.** The corpus build needs no CMS key and
  makes no API calls. Plan ingestion needs both — tens of thousands of
  requests at full scope — so it is a command you run deliberately, per
  state, not a stage of `make ingest`.

### Surrogate UUID keys, with HIOS ids as named unique constraints

Every table has a UUID primary key; `hios_plan_id` and `hios_issuer_id` are
unique only together with `plan_year`. This follows the one existing
precedent — `chunks.chunk_id` is a unique external identifier beside a
surrogate key — and it is also forced: a HIOS plan id recurs every year, so
a natural key would be `(hios_plan_id, plan_year)`, and every child table
would have to carry both columns in its foreign key.

The constraints are named explicitly (`uq_plans_hios_plan_id_plan_year`, …)
because ingestion's upserts target them by name, and `Base.metadata` has no
naming convention to make generated names stable.

### `premium_reference` is a fixed 27-year-old, set in code

The premium is the only catalog field that depends on the household — the
same plan cost $323.30 at 25 and $718.08 at 55. The stored figure is the
unsubsidized premium for a single 27-year-old, CMS's own convention for
comparing premiums, and every request sends that household explicitly.
Omitting it does not mean 27: CMS applies its own undocumented default.

The age is a module constant, not a setting. It defines what the column
*means*. A configurable age would let two environments store premiums that
cannot be compared, with nothing in the row recording which age produced
them.

### The cost-share key includes the deductible's type

A plan can carry a $0 medical and a $5,500 drug deductible under an
identical CSR variant, network tier and family split — found by sampling
real plans before the schema was written. So `plan_cost_shares` is unique on
all six of plan, kind, type, CSR variant, network tier and family split.
Every one of those columns is `NOT NULL`, with a missing value stored as
`""`: Postgres treats NULLs in a unique constraint as distinct, so a single
nullable key column would let every re-sync insert duplicates without an
error.

### Cascading foreign keys, despite ADR 0007

ADR 0007 deliberately left `message_sources.chunk_id` without a foreign key,
because a corpus rebuild would otherwise erase conversation history. That
reasoning is about *history*. `plan_cost_shares` and `plan_counties` are
*current state* written by the same sync as their plan: a plan that leaves
the catalog should take them with it. Both foreign keys cascade.

What protects history from plan re-ingestion is the same rule ADR 0007
applied — Step 5's `message_plans` will record the HIOS id as a plain
string, with no foreign key. That is what keeps these cascades safe.

## Consequences

**Re-runs are safe, and verified.** Issuers and plans are upserted on their
named constraints; cost shares are replaced per plan, so a variant dropped
upstream does not linger. Ingesting two Texas counties twice left all four
tables with identical row counts and identical data fingerprints. Each
county is one transaction, so an interrupted run keeps what it finished,
and a county that fails is reported and skipped.

**Full scope is slow, by nature.** Plans are sold per county, and each
county takes about 14 paged requests. One state is thousands of requests;
all 30 are tens of thousands — hours at the ~0.2 s pacing chosen to stay
well inside a free public API's limits. `--max-counties` exists for quick
checks.

**One known gap in coverage.** An issuer may serve only part of a county.
Each county is searched with one representative ZIP, so such a plan can be
missed. The failure is always an omission, never a plan recorded in a county
that does not sell it.

**The API key needs active protection.** CMS takes it as a query parameter,
and `requests` embeds the full URL in HTTP, connection and timeout errors.
The client re-raises every failure with only method and path, and a test
pins that for both kinds of error.

**Deferred, deliberately.** Per-service benefit detail — the copay for a
given visit type — is roughly fifty benefit types across three tiers per
plan, and nothing yet reads it. There is no `plan_benefits` table until a
feature needs one.
