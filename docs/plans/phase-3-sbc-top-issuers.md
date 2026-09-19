# Phase 3 — SBC for the largest issuers

**Status:** Complete (ADR 0015). Results are in
[docs/findings/sbc-documents.md](../findings/sbc-documents.md#phase-3-the-largest-issuers).
**Depends on:** [Phase 2](phase-2-sbc-narrow-slice.md), plan-scoped retrieval
proven on a corpus small enough to check by hand.

## Goal

Extend SBC coverage from the Phase 2 slice to the **largest issuers**, for the
current plan year. Keep the fetch list bounded and known, instead of taking on
the long tail of small regional carriers in the same step.

## What was built

- **The largest issuers.** The ten largest parent companies by 2025 average
  monthly enrollment in the 30 HealthCare.gov states (CMS's Issuer Level
  Enrollment PUF), with Aetna left out after its 2026 exit. They are listed
  with their HIOS issuer IDs in `src/ingestion/sbc/top_issuers.py`. Together
  they are 76.6% of enrollment.
- **The states.** FL, TX, NC, TN, AL and SC, plus Phase 2's NH and DE: the
  catalog for each state, then the top issuers' SBCs.
- **Ingestion that scales:**
  - a document is parsed once per `PARSER_VERSION`, so a run with nothing new
    makes no request;
  - every downloaded PDF is kept (ADR 0016; ADR 0015 first deleted them);
  - `TOP_ISSUERS=1` or `ISSUERS=…` narrows a run to the listed issuers.

## What this phase tested, and what it found

The first draft of this document expected SBC chunks to share the corpus's
`chunks` table and hybrid search. ADR 0014 kept them apart instead, in
`sbc_chunks`, without embeddings, and reached only through one plan's
document. That changed which questions scale could break.

- **Retrieval quality as the corpus grows: holds by construction.** A coverage
  question reranks one document's ~25 sections, however many documents exist.
  On the new issuers, the right section reached the model for 200 of 200
  question–plan pairs.
- **The 0.5 relevance gate: unaffected.** SBC text never passes through
  general search or its gate.
- **The HNSW index: not needed.** `chunks` did not grow; it still holds 1,568
  rows.
- **Eval floors on existing questions: unaffected.** General search cannot
  return SBC text, so no definitional question can surface one plan's numbers.
  Every existing eval set was re-run anyway, three times.
- **Ingestion stays tractable, once parsing is incremental.**
  - The catalog for six states took about 31 minutes.
  - The SBC tuning pass took 794 s for 829 documents.
  - A run with nothing new makes no request for a stored document. It still
    retries every failure: 125 s, most of it BCBS of North Carolina's 57
    challenged links at two seconds each.
- **Access is what limits coverage, not the parser.**
  - Of the ten parents, Oscar, UnitedHealthcare, Elevance and BCBS of South
    Carolina refuse automated requests. BCBS of North Carolina serves a bot
    challenge.
  - 890 of the top parents' 1,410 plans in the eight states have an SBC.
  - The parser needed one fix.
- **Plan-year drift.** No document was `wrong_year`. The check stays in place.
- **Issuer IDs drift between years.** Three 2026 issuer IDs of top parents
  were not in the 2025 enrollment data. They were found by comparing the
  catalog with the list, which is now a step in the runbook.

## Out of scope

- The long tail of small regional carriers — Phase 4
- Re-fetching changed documents, and the refresh cadence — Phase 4
- Prior plan years
- State-based exchange plans
- EOC documents
