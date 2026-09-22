# Phase 4 — SBC across all 30 HealthCare.gov states

**Status:** complete, 20 September 2026 — built for **eighteen** states, not
thirty. The ten largest unloaded states were added to Phase 3's eight, which
is 93.1% of HealthCare.gov enrollment; the remaining twelve, under 7% between
them, were left out deliberately (ADR 0015, "Phase 4's scope"). Every issuer
in the eighteen was read, not only the largest parents.
What the run measured is in
[`docs/findings/sbc-documents.md`](../findings/sbc-documents.md), the
decisions it produced are ADRs 0017, 0018 and 0019, and keeping it current is
[`docs/runbooks/sbc.md`](../runbooks/sbc.md).
**Depends on:** [Phase 3](phase-3-sbc-top-issuers.md) — scale behaviour
measured and indexed

## Goal

Complete SBC coverage of the federal marketplace: **all 183 QHP issuers across
all 30 HealthCare.gov states**, current plan year.

This is the ceiling of what the Marketplace API can support. Beyond it lie the
21 state-based exchanges, each a separate integration — out of scope for the
roadmap as written.

## What is new here

Phases 2 and 3 dealt with known issuers publishing documents predictably.
This phase is mostly about the **long tail**, and its problems are
acquisition problems rather than retrieval problems:

- Small regional carriers with inconsistent or absent document URLs
- SBCs behind interstitials, or served as scanned images rather than text
- Plan-year labelling that does not match the catalog
- Issuers who publish one SBC covering several plan variants
- URLs that rot between ingest runs

Each is a data-quality decision, not a code decision. Decide and record what
happens when a plan has no retrievable SBC: the plan must still appear in
comparison (its structured data is intact from Phase 1) while being honestly
marked as having no document behind it.

## Coverage tracking

At this scale "did ingestion work?" stops being answerable by eye. The
pipeline needs to report, per plan year:

- plans in the catalog
- plans with a resolved SBC URL
- plans with successfully extracted text
- plans that failed, and why

Partial coverage is the steady state, not a bug. The number that matters is
whether it is improving and whether failures are understood.

## The honesty requirement

This is where the application is most likely to mislead. A user comparing ten
plans where six have SBC text and four do not will read the answer as
uniform unless told otherwise. Silence about a missing document reads as
"nothing excluded."

Surface the gap in the answer and in the plan card. An unanswerable question
about a plan with no document must say so rather than falling back to generic
corpus prose — which will otherwise happen automatically, because unconditional
retrieval always has Wikipedia chunks available to fill the context.

That interaction is worth stating plainly: **the merged-context design makes
missing plan data fail quietly rather than loudly.** Guard it with an eval
case.

## Re-measure everything, again

Same discipline as Phase 3, at a larger corpus: retrieval floors, gate
calibration, HNSW parameters, ingestion runtime. Record the numbers.

## Maintenance

Phase 4 is the first phase that does not end. Plan years roll over annually;
documents change mid-season; issuers enter and leave the marketplace. Decide
the refresh cadence and what triggers a re-ingest, or the corpus silently ages
into being wrong.

## Out of scope

- State-based exchange plans (21 states + DC) — a separate integration per
  state, and no shared API
- Prior plan years, beyond whatever retention the refresh policy sets
- Employer, Medicare and Medicaid plans — no public catalog exists
- EOC documents
