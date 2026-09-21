# 0017 — Saying which plans have no document

## Status

Accepted. Phase 4 (docs/plans/phase-4-sbc-full-coverage.md, "The honesty
requirement"). Amends ADR 0014's status table and ADR 0007's sources, for
coverage answers only.

## Context

Phase 4 reads every issuer's SBCs in more states, so plans without SBC text
become common, not rare. Phase 3 left 403 of 896 attempted documents blocked,
and 56 more behind a bot challenge. A user comparing ten plans, four of them
without a document, reads the answer as uniform unless told otherwise.

Before this change, nothing said which plans those were:

- **`plan_coverage` merged six failures into `unavailable`**, and dropped the
  reason. The model couldn't tell a refusal from a document for the wrong year.
- **`search_plans` said nothing** about documents, so a comparison couldn't
  name the plans it had no document for until it had tried each one.
- **The plan card linked "Plan summary"** for every plan, read or not.
- **Every retrieved corpus chunk was saved as a source,** cited or not. Retrieval
  always runs (ADR 0010), so a coverage answer about a plan with no document
  still listed Wikipedia and HealthCare.gov pages beneath it, as if they backed
  it.
- **The eval printed how many corpus chunks came back,** but never failed an
  answer for citing them.

The roadmap names the risk: the merged-context design makes missing plan data
fail quietly, because general material is always there to fill the gap.

## Decision

### One status per plan, from the catalog to the card

A plan's SBC status is one of:

- `ok`: its document was read, whole;
- `partial`: its document was read, but without all of the template's
  questions or its costs chart (see below);
- `no_link`: HealthCare.gov lists no SBC for it;
- `not_read`: it has a link that has never been read;
- the document's own failure: `blocked`, `http_error`, `not_pdf`,
  `too_large`, `wrong_year` or `unparseable`.

It is worked out in one place, `src/services/sbc_status.py`. That is an outer
join from the plan to `sbc_documents` on the same link and year; a document is
unique on those two, so the join adds no rows.

- **`search_plans`** gives the model `sbc_readable` for each plan and, when
  false, `sbc_missing_reason`. The model knows which plans have no document
  before it calls `plan_coverage`.
- **`plan_coverage`** keeps its coarse status (`ok`, `not_found`,
  `no_document`, `unavailable`) and adds the reason.
- **Reasons are sentences written in that module,** never the stored `detail`,
  which can hold an HTTP code or robots wording meant for the ingest report.

### A document read in part says so

Phase 4's run found 62 documents of 1,189 whose PDF gives up its text but not
all of the template: the chart is drawn in a way that yields no table, or the
questions column interleaves its answers. Recorded as `ok`, they are the same
silent failure this ADR exists to stop — an answer would search a document
that has no prices in it and conclude the plan says nothing.

- **Its text is kept and searched.** What was read is the plan's own words,
  and half a document beats none.
- **`sbc_readable` stays true,** and `plan_coverage` still returns its
  passages, but `sbc_missing_reason` says what is absent.
- **The prompt closes the gap:** when no passage answers and the document is
  partial, the answer says the part that would answer isn't among what was
  read, and links the PDF — never that the plan doesn't cover it.
- **The completeness rule is the template's own:** all seven Important
  Questions, and at least the chart's ten "If you…" groups. 1,127 of 1,189
  documents meet it.

### The plan card keeps the status it was shown with

`message_plans.sbc_status` is a snapshot, as ADR 0011's premiums are.

- **A refresh may read a document later;** the card still says what was true
  when it was shown.
- **NULL means the card predates this change.** It is never read as "readable".
- A CHECK constraint limits it to the statuses above.

### The guard is the prompt and the eval, not code

`COVERAGE_PROMPT` now says:

- a plan with no readable document has no source here for what it covers;
- the answer names the plan, with the reason;
- it never describes the plan's coverage, costs or exclusions, whether from
  `<retrieved_context>` or from another plan's passages;
- **then it stops.** It adds no general rules about what plans usually cover
  or cost, and no definitions, unless the user asked what a term means. The
  first eval run showed why: asked whether a blocked plan covers preventive
  care "for free", the answer named the plan, linked its PDF, and then added
  "General Marketplace rules: … at no cost". The label said "general"; a reader
  comparing plans would still take it as that plan's terms;
- a comparison names every such plan beside those it could read, and any plan
  it didn't read.

Dropping corpus chunks in code was considered and rejected. A coverage question
often asks a definition too ("does it cover MRIs, and what is coinsurance?"),
and a code-level guard can't tell which half a chunk serves.

The eval enforces the rule instead. `scripts/eval_generation.py` scores
coverage answers on the answer's own text:

- **`CORPUS`:** it cites general material. Only the definitional case may.
- **`SILENT`:** it doesn't name a plan whose document couldn't be read.
- **`FABRICATED`:** it states a dollar or percent figure when no plan's
  document was read. Figures inside the linked PDF address, or in the plan's
  own name ("$10 Tier 1 Rx"), don't count.
- **`FIXTURE`:** a plan the case expects to be missing has since been read. The
  case fails as a fixture, never as a pass.

A new MISSING DOCUMENTS set has a full-marks floor:

- a bot-challenged plan;
- a blocked plan asked about preventive care, which the corpus does describe
  in general;
- a three-plan comparison with one plan blocked;
- a blocked plan asked for figures.

### A coverage answer lists only the sources it cites

When an answer called `plan_coverage`, a corpus chunk is saved as a source only
if the answer cites its label inside `[Source: …]`.

- **Coverage answers cite inline,** because the coverage prompt requires it, so
  an uncited chunk there was not used.
- **Other answers keep every retrieved chunk,** as ADR 0007 decided. Most
  definitional answers don't cite inline, and the sources list is how they show
  their grounding.
- The chunks still reach the model in both cases; only what is saved and shown
  changes.

## Consequences

- **A missing document is visible in three places:** the answer names the plan,
  the card shows its status (the frontend change follows this one), and the
  eval fails an answer that describes it.
- **Plan search gains a join.** It is on the unique `(url, plan_year)` index.
  The Phase 4 findings measure it on the largest counties.
- **The guard is only as good as the model's compliance.** The eval catches
  regressions; it cannot prove every answer complies. Its cases pin a plan's
  status, so each needs updating if that plan's document is ever read.
- **ADR 0014's table gains a column,** the precise status. Its coarse statuses
  and their prompt rules are unchanged.
