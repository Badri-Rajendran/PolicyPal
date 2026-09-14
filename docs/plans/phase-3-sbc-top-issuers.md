# Phase 3 — SBC for the largest issuers, nationally

**Status:** documented only, not built
**Depends on:** [Phase 2](phase-2-sbc-narrow-slice.md) — plan-scoped retrieval
proven on a hand-verifiable corpus

## Goal

Extend SBC coverage from one or two states to the **8–10 largest issuers
across all 30 HealthCare.gov states**, current plan year.

This covers most enrollees while keeping the fetch list bounded and
well-known, rather than taking on the long tail of small regional carriers at
the same time as the first scale-up.

## Why this comes before full coverage

It is the smallest step that tests *scale* rather than *correctness*. Phase 2
proved the retrieval semantics on a corpus small enough to verify by hand;
this phase finds out what breaks when the corpus grows by an order of
magnitude, with a document set that is still enumerable.

A long tail of small carriers adds acquisition failure modes — dead URLs,
non-standard hosting, inconsistent plan-year labelling — without adding much
enrollee coverage. Defer those to Phase 4, where they are the whole point.

## What this phase is actually testing

**Does retrieval quality hold as the corpus grows?** The concern is not
correctness of the filter — Phase 2 settled that — but recall. With many more
near-identical SBC chunks competing, a plan-scoped query narrows to a smaller
candidate set, which may interact badly with the hybrid BM25 + dense split
(`sparse_top_k = 20`, `dense_top_k = 30`). Those values were tuned for a
1,568-chunk corpus.

**Does the 0.5 relevance gate still behave?** `min_relevance_score` was
calibrated on definitional prose. SBC text is terse, tabular and repetitive;
its score distribution will differ. Re-measure rather than assume.

**Is ingestion still tractable?** Time a full run and record it. If it stops
being something you can run casually, incremental ingestion stops being an
optimisation and becomes load-bearing.

## Vector index

`chunks.embedding` has no HNSW index. At Phase 2 scale a sequential scan is
fine; somewhere in this phase it stops being fine.

Add the index when a measurement says to, not before — and record the
before/after query times. pgvector's HNSW parameters trade build time and
recall; pick them from measured behaviour on the real corpus.

## Acquisition at scale

- The issuer list is bounded and known, so the fetch list can be checked in
  rather than discovered
- Caching and resumability from Phase 2 become mandatory rather than polite
- Expect plan-year drift: an issuer may publish next year's SBC mid-season.
  `plan_year` is part of chunk identity, so this must be detected, not merged
- Budget for re-fetching. Documents change without notice

## Eval floors

The existing coverage and routing floors were measured against a
Wikipedia + HealthCare.gov corpus. Adding thousands of SBC chunks changes what
`search()` returns for *existing* questions too — a definitional query may now
surface SBC text that outranks the glossary chunk it used to find.

Re-run every eval and reset floors deliberately. Treat a changed number as a
finding to explain, not a threshold to lower.

The plan-scoped retrieval test from Phase 2 becomes more important here, not
less: more near-identical documents means more opportunities to cross plans.

## Out of scope

- The long tail of small regional carriers — Phase 4
- Prior plan years
- State-based exchange plans
- EOC documents
