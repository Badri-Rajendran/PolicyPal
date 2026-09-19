# Phase 2 — SBC ingestion, narrow slice

**Status:** Complete. Ingestion (ADR 0013) and plan-scoped coverage answers
(ADR 0014) are built; results are in docs/findings/sbc-documents.md
**Slice:** New Hampshire and Delaware, all issuers, plus the two Texas counties
already loaded
**Depends on:** [Phase 1](phase-1-marketplace-api.md) — plan IDs and issuer
document URLs come from the catalog

## Decisions made while building it

The user settled these at the start of the phase. Most depart from the text
below, which is kept as the original analysis.

- **SBC text lives in its own table, `sbc_chunks`, not in `chunks`.** It is
  reached through a plan-scoped tool, never through the unconditional
  `search()`. General search then cannot return one plan's numbers for a
  definitional question, with no filter for every query to remember. See
  ADR 0014, which replaces "Retrieval" and "Cross-plan retrieval" below.
- **Slot competition is avoided by construction.** SBC passages arrive through
  the tool and do not take corpus slots. It is still measured.
- **Incremental ingestion without touching `chunks`.** `make ingest` still
  rebuilds the corpus. SBC ingestion replaces one document at a time
  (ADR 0013). ADR 0007's reasoning is unchanged.
- **Situational questions** ("will my MRI be covered?") get a fixed boundary
  sentence plus the plan's SBC terms, never a yes/no verdict.
- **No issuer PDF is committed.** Parser tests use hand-written pages in the
  template's shape, and real documents are verified by the live ingest
  (docs/findings/sbc-documents.md).

## Goal

Ingest Summary of Benefits and Coverage documents for **one or two states, all
issuers, current plan year** — roughly 200–800 SBCs. Prove that plan-scoped
retrieval works before scaling it.

The narrow slice is the point. At this size the corpus is hand-verifiable, so
eval floors stay meaningful and a retrieval bug is findable. Phases 3 and 4
only make sense once this holds.

## Why the SBC

Evidence of Coverage documents are not obtainable before purchase — see the
[roadmap](README.md#evidence-of-coverage-is-not-obtainable-the-sbc-is). The
SBC is federally mandated, standardized, ~8 pages, and provided when shopping.

It carries what this phase needs: a "Services Your Plan Does NOT Cover"
section, limitations and exceptions, and worked coverage examples.

The standardized federal template is the technical advantage. Identical
section headings across every issuer means chunking can be **structure-aware**
rather than recursive-by-length, and the same heading always means the same
thing — so a chunk's section is usable metadata, not a guess.

## Retrieval

SBC chunks go into pgvector alongside the existing corpus and are retrieved by
the same unconditional `search()` path. They reach the LLM context exactly as
corpus chunks do, and merge with plan rows in one answer.

## Two risks to design for

### Cross-plan retrieval

`chunks` today has only `content`, `source`, `chunk_id`, `embedding` — no plan
identity, no plan year. With SBCs for hundreds of plans in that flat table, a
question about an Aetna silver plan can retrieve chunks from a Cigna bronze
plan and produce a confident answer *with a citation attached*.

Reranking will not catch it.
[ADR 0004](../decisions/0004-retrieval-tuning.md) already states why:

> "A cross-encoder scores topical relatedness, not answerability, and no
> threshold separates the two."

Two SBCs are maximally similar — same federal template, same headings, same
vocabulary — and differ only in their numbers. That is precisely the blind
spot.

**Recommended fix:** `chunks` gains `plan_id` and `plan_year`, and `search()`
gains an optional metadata filter applied **before** retrieval rather than
reranking after. A plan-scoped question narrows the candidate set first; a
general definitional question passes no filter and searches everything.

### Slot competition

SBC chunks and corpus chunks compete for the same `rerank_top_k = 5` slots
(`src/policypal/config.py`). A plan-specific question could fill all five with
general Wikipedia definitions, leaving no room for the SBC text that actually
answers it.

Measure this once real SBCs are in. The likely answer is a per-source
allocation rather than one global top-k — but do not design it before there is
a measurement to justify it. ADR 0004 set `rerank_top_k` to 5 on evidence;
change it the same way.

## Acquisition

- Plan IDs and issuer document URLs come from the Phase 1 catalog
- SBCs are PDFs. `src/ingestion/html_text.py` handles HTML, not PDF — a PDF
  extractor is a new dependency and should be chosen deliberately, pinned, and
  scanned like every other (CLAUDE.md)
- Fetching must be polite: rate-limited, cached on disk, resumable. Do not
  re-download on every ingest run
- Expect failures. Some URLs will 404 or point to the wrong plan year. Fail
  with an actionable message naming the plan, as the ingestion pipeline
  already does when no source produces chunks

## Ingestion pipeline

`make ingest` currently calls `embed.execute(rebuild=True)`, which deletes all
`chunks` rows. That is survivable for 1,568 corpus chunks and not survivable
here.

This phase needs **incremental ingestion**: upsert by `chunk_id`, leave
untouched sources alone. Note the knock-on effect — ADR 0007 gave
`message_sources.chunk_id` no foreign key precisely *because* `rebuild=True`
cascades history away. If rebuild stops being the default, revisit whether
that reasoning still holds.

## Plan-year versioning

A 2025 SBC answering a 2026 question is wrong, and confidently so. The corpus
already has a moving-cutoff filter for dated HealthCare.gov content; this is
the same problem with higher stakes, because the answer is about money the
user will actually pay.

`plan_year` is part of the chunk identity, not a display field.

## The refusal boundary

This becomes the highest-stakes line in the application:

| Answerable from an SBC | Not answerable |
| --- | --- |
| "Does this plan cover MRIs?" | "Will my MRI be covered?" |
| "What's the ER copay?" | "Will they pay for my ER visit last Tuesday?" |
| "What's excluded?" | "Is my condition a pre-existing condition?" |

The second column turns on medical necessity, prior authorization, network
status and claims adjudication — none of which is in any document PolicyPal
can obtain. ADR 0004 already records that abstention is unreliable and that no
threshold separates topical relatedness from answerability.

Treat this as an explicit eval set with its own floor, in the spirit of the
existing `ABSTENTION_SET`, rather than trusting the prompt alone.

## Copyright

SBCs are government-mandated standardized forms, which is a materially weaker
copyright claim than a bespoke EOC contract — but not zero. ADR 0003 already
rejected state insurance department guides on copyright grounds, so the
project has a precedent to be consistent with.

Record the decision in an ADR rather than letting it pass silently. The
README's "educational and portfolio purposes" framing is relevant context, not
a blanket answer.

## Tests and evals

- Structure-aware chunking of the federal template, on real fixture documents
- Plan-scoped retrieval: a question about plan A must never return plan B's
  chunks. This is the phase's headline test
- Slot-competition measurement, with numbers recorded
- Refusal-boundary eval set with a floor
- Plan-year correctness: a question with a year must not match another year

## ADRs

- SBC as the document source, and why not EOC
- Plan-scoped retrieval via pre-retrieval metadata filtering
- Copyright and redistribution posture

## Out of scope

- More than two states — Phases 3 and 4
- Prior plan years
- EOC documents
- Dental (SADP) plans, unless the narrow slice happens to include them
