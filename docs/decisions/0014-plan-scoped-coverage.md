# 0014 — Plan-scoped coverage answers from the SBC

## Status

Accepted. Phase 2, second half. Ingestion is ADR 0013.

## Context

ADR 0013 stores each plan's Summary of Benefits and Coverage (SBC) as one
chunk per template section, in `sbc_chunks`. The answers it can give are about
one plan: "does the second one cover MRIs?", "what's the ER copay on the
Highmark bronze?".

Three things about the existing pipeline shape how:

- **General retrieval is unconditional** (ADR 0010). It runs on every question
  and passes whatever clears the relevance gate to the model.
- **Every SBC uses the same headings.** Ten plans' "If you have a test"
  sections differ only in their numbers, so a search over all of them would
  hand the model one plan's figures for another plan's question.
- **Plan IDs don't reach later turns.** History is text only, so "the second
  one" can't be resolved from it.

## Decision

### A tool, not a filter on search

The model gets a second tool, `plan_coverage(plan_ids, question)`, beside
`search_plans`.

- **General search never sees SBC text.** SBC chunks sit in their own table
  (ADR 0013), so no filter has to be remembered on every query. A definitional
  question ("what is a deductible?") can't be answered with one plan's
  numbers.
- **The tool is offered only when the plan catalog is loaded**, like
  `search_plans`.
- **The existing two tool rounds are enough.** A turn can search in the first
  round and read coverage in the second. It can also read coverage in the first
  round for plans already on screen.

### Retrieval within one plan: rerank everything, gate nothing

- **Reranked, not embedded.** A plan has 25–26 chunks, so the cross-encoder
  scores every one of them against the question and the top 4 are returned.
  That makes embeddings and an index unnecessary for this table.
- **No relevance gate.** ADR 0004 measured the reranker score as a ranking
  signal, not a test of whether a passage answers the question. Within one
  plan's SBC the right section is almost always present; it just scores low
  when the question's words differ from the template's ("MRI" against
  "Imaging (CT/PET scans, MRIs)"). The model is told to answer only from what
  the passages say. Scores are kept on the citation and logged.
- **Chunks are joined through the plan's own year.** A plan reaches its
  document through `plans.benefits_url` and `plans.plan_year`. A 2025
  document at the same URL is never used for a 2026 plan.

### Which plan is meant: `<plans_shown>`

The server hands the model the plans that were shown last in the thread: the
most recent assistant message that has plan cards (ADR 0011), in the order
shown.

- **The block carries position, plan ID, name, issuer, metal level and year.**
  No premiums or deductibles: it exists to resolve "the second one", and the
  prompt says it is never a source of facts.
- **Its text is untrusted data.** Plan and issuer names come from CMS, so the
  block is delimited and neutralized like retrieved context.
- **A plan's year comes from where the plan was shown**, so a follow-up about
  a 2026 plan stays on 2026 even after the next year is loaded. An ID the
  model supplies from elsewhere resolves to the latest catalog year.

### Each plan's status is reported, never guessed

| Status | Meaning | What the answer says |
| --- | --- | --- |
| `ok` | Passages returned | The terms, cited |
| `not_found` | No such plan in the catalog | Ask which plan is meant |
| `no_document` | The plan has no SBC link, or it was never fetched | Point to HealthCare.gov |
| `unavailable` | The SBC was fetched but could not be used, e.g. the issuer's host refused automated requests | Link the issuer's PDF |

### Situational questions get terms, never a verdict

"Will my MRI be covered?" depends on medical necessity, prior authorization
and the provider's network, and none of that is in an SBC. The answer opens
with one fixed sentence:

> I can't tell whether a specific claim will be paid; that depends on medical
> necessity, prior authorization and your provider's network.

Then come the plan's cited SBC terms. It never says yes or no.

### Citations

- **Each passage is a `MessageSource`**, persisted by the existing code with
  no schema change.
- **Its label is `"{plan name} - Summary of Benefits - {section}.pdf"`.** Its
  `chunk_id` is the SBC chunk's.
  - Plans that share one document get one label each, so both show up.
  - The trailing `.pdf` exists for the frontend's `formatSourceLabel`, which
    strips everything after the last dot. Without it, a plan name like
    "Silver 2.0" would lose its end.
- **In the answer text, https links are clickable** through the frontend's
  existing `safeUrl`. That is how an `unavailable` plan's PDF is reached.

## Consequences

- **Tokens.** A coverage answer adds a second or third model call and up to
  12 passages (3 plans × 4). The eval records the measured cost.
- **Low-scoring passages still reach the model.** The prompt's "only what the
  passages say" rule carries the grounding, and the boundary eval checks it.
- **Sources show real scores.** A coverage citation's "% match" can be low
  even when it holds the answer.
- **Plans shown before the last plan table can't be referred to by position.**
  Only the most recent table is handed over.
