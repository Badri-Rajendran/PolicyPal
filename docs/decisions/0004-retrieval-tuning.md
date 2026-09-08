# 0004 — Retrieval tuning: context width and multi-intent queries

## Status

Accepted

## Context

Two defects surfaced once the corpus grew (ADR 0003) and the eval could
finally measure coverage rather than only routing.

### 1. `rerank_top_k` was buying nothing

Every answer cited up to 15 sources, most of them at a displayed relevance of
1.00 — the cross-encoder's sigmoid saturates, so "very relevant" and
"somewhat relevant" both render as 1.00 and the citation list stops carrying
information. On the denser corpus, tangential chunks were clearing the gate
alongside good ones.

Measured across the coverage and routing sets:

| `rerank_top_k` | answered | evidence | routing (top-5) | avg citations |
| --- | --- | --- | --- | --- |
| 5 | 16/20 | 16/20 | 25/25 | 4.4 |
| 8 | 16/20 | 16/20 | 25/25 | 6.5 |
| 10 | 16/20 | 16/20 | 25/25 | 7.6 |
| 15 | 16/20 | 16/20 | 25/25 | 9.8 |

Retrieval quality is *identical* at every value. The extra ten chunks bought
nothing except citation noise and 3x the context a 0.5B model has to stay
grounded in.

### 2. Compound questions silently returned nothing

The coverage eval reported *"What does 'in-network' mean and why does it
matter?"* as a corpus gap. It wasn't — the corpus holds an excellent CMS
definition of `Network`, and both sparse and dense search put it in the
candidate set every time. The reranker was dropping it:

| Query | Top relevance | Above the 0.5 gate |
| --- | --- | --- |
| `What does 'in-network' mean and why does it matter?` | 0.487 | no — **0 results** |
| `What does 'in-network' mean?` | 0.977 | yes |
| `What does in-network mean and why does it matter?` | 0.568 | barely |
| `What does in-network mean?` | 0.993 | yes |

The quotes are not the cause; the conjunction is. A cross-encoder scores one
(query, passage) pair, so it answers "does this passage address the *whole*
query". No single chunk addresses both halves of a compound question, and the
score collapses far enough to fall under the relevance gate. Compound
questions are ordinary user phrasing, so this failed a whole class of real
queries, invisibly, by returning nothing at all.

## Decision

### `rerank_top_k` 15 → 5

Set from the measurement above, not from taste. Recorded here because it is
the kind of number that gets "tuned" back up later without evidence.

### Decompose multi-intent queries, but only as a fallback

When a query splits on `and`/`or` into two or more substantial fragments
(≥3 words each), rerank against each fragment and keep every chunk's best
score.

**This runs only when the query as a whole cleared the gate with nothing.**
Making it a fallback rather than the default is the important part: a
best-of-several score can only ever be higher, so applying it universally
would inflate scores across the board and quietly weaken the relevance gate
that exists to stop weak context reaching the LLM. As a fallback it is
strictly additive — every query that already worked behaves byte-for-byte as
before, and only the ones currently returning nothing get a second chance.

A syntactic split was chosen over an LLM-based query rewrite (multi-query,
HyDE). It costs no extra model call, is deterministic, and is directly
targeted at the measured cause. Reaching for a generative rewriting step
here would add latency, cost, and a second prompt-injection surface to solve
a problem that a regex and a max() solve.

### Fix the eval to measure what production serves

The coverage eval called `search(query, top_k=5)` while the API called
`answer_query(content)` with no `top_k`, which resolves to
`settings.rerank_top_k` — 15 at the time. The eval was measuring retrieval
the application never performed. Coverage now passes no `top_k` so it
exercises the configured production path; routing still asks for a fixed
window because it is scored by rank.

### Guard abstention as a measured property

While checking the remaining gaps, one coverage question turned out to be
wrong rather than unanswered. *"Term life or whole life — which is better for
a young family?"* returns nothing, and that is **correct**: it asks for a
personalized recommendation, which a grounded assistant should not
manufacture from an encyclopedia article. The corpus answers the factual form
— *"What is the difference between term life and whole life insurance?"* — at
1.00. The eval case was replaced with the factual form.

The abstention itself is now asserted. `ABSTENTION_SET` lists advice and
prediction questions verified to return nothing, with its own floor. This
guards precisely the regression the subquery change could have introduced: a
lower gate, or best-of scoring applied to every query rather than only to
ones that matched nothing, would start answering these from whatever chunk
was topically nearby.

**Known limitation, stated rather than hidden:** abstention is not reliable
across the board. *"Should I sue my insurance company?"* returns the D&O
liability article at 0.97, and *"Which insurance company should I buy from?"*
scrapes the gate at 0.55 with a title-insurance chunk. A cross-encoder scores
topical relatedness, not answerability, and no threshold separates the two.
Only the verified-abstaining questions are in the set; the rest are recorded
here as an open problem. The mitigation that already exists is the generation
prompt, which instructs the model to answer only from the supplied context.

### Add three Wikipedia articles

`Umbrella insurance`, `Term life insurance`, `Whole life insurance` — named
by the coverage eval as genuine gaps (0.146 and 0.003 top relevance, no
plausible source in either corpus). These are real absences rather than
retrieval faults, and the existing Wikipedia source ingests them with no new
integration.

## Consequences

Every answer now cites roughly half as many sources, with no measured loss in
what those sources support. Compound questions return the answer the corpus
already contained.

Coverage moved from 16/20 to 19/20 answered and 19/20 with evidence, with
routing unchanged at 25/25.

The one remaining unanswered question is *"How do I file a claim after a car
accident?"* — genuinely absent, since Wikipedia is encyclopedic about auto
insurance and HealthCare.gov is health-only. Closing it means a source
covering auto claims procedure; the candidates and their licensing are
already assessed in ADR 0003.

The subquery fallback is a heuristic and will not decompose every multi-intent
phrasing (an implicit "what is X, how do I get it" without a conjunction still
scores as one query). It addresses the measured failure, not the general
problem, which is the reason it is cheap enough to justify.
