# 0008 — Hosted LLM for generation

## Status

Accepted

## Context

Phase 1 (`docs/plans/phase-1-marketplace-api.md`) needs reliable tool
calling: the model must decide when to call `search_plans` and produce
well-formed arguments for it. `Qwen/Qwen2.5-0.5B-Instruct`, the local model
answer generation ran on, does not do this reliably — it produces malformed
arguments and misses calls it should make.

Upgrading locally was not open either. The 1.5B variant of the same family
exceeded the project's RAM budget and thrashed swap, which is why the
project sat on 0.5B in the first place rather than a straightforward step up
within the same family.

No prior ADR covers the local model choice; it only ever appeared as a
changelog line. Nothing here supersedes an existing decision, but reversing
local-only inference is the most material architectural change the project
has made since ADR 0001, and CLAUDE.md requires recording material choices.

## Decision

Answer generation moves to OpenAI's hosted API: `gpt-5-mini` for answers,
`gpt-5-nano` for the cheaper query-rewrite step (ADR 0005). Embeddings
(`bge-small-en-v1.5`) and the reranker (`ms-marco-MiniLM-L-6-v2`) stay local,
so ingestion and retrieval remain free and offline — only generation now
depends on a network call and a paid API.

## Consequences

### `temperature` is gone

`gpt-5-mini` accepts only the default temperature; the API rejects any other
value. It was set to `0.2` specifically to keep grounded QA deterministic
and reduce hallucination. Grounding now rests entirely on the system prompt
and the `min_relevance_score` 0.5 gate — there is no sampling-level lever
left to pull.

### The output cap covers reasoning tokens, not just the reply

Measured 64–128 reasoning tokens spent before any visible text, for both
models. The rewrite cap was 48 under the old model; at that cap the response
comes back empty (`finish_reason: length`, no error), and
`rewrite_query()` falls back silently on empty output. Follow-up questions
would have quietly stopped resolving against the conversation — undoing ADR
0005 — with nothing but a debug-level "rewrite rejected" log line to notice
it by. Caps are now 512 (answers) and 192 (rewrites).

### `reasoning_effort` is `"low"`

Measured identical output quality to `"medium"` at roughly half the
reasoning tokens, so `"low"` is the default (`src/policypal/config.py`).

### Pinned revisions are lost

`llm_model_revision` pinned a Hugging Face commit SHA for the local model,
giving a CWE-494 (download of code without integrity check) mitigation:
behaviour couldn't change without a version bump the project chose. A hosted
model has no equivalent — `gpt-5-mini` and `gpt-5-nano` are OpenAI-managed,
and their behaviour can change server-side with no signal to this project.
That posture is weaker for this one component; embeddings and the reranker
keep their pinned revisions unchanged.

### PII egress is accepted and disclosed

A user typing "silver plans in 60601, I'm 34" sends that ZIP code and age to
OpenAI in the raw message, before any tool call exists to structure or
redact it. CLAUDE.md asks to keep PII out of prompts; this decision accepts
the egress rather than blocking it, on the basis that redaction before a
tool exists to use structured fields would be premature and would degrade
answer quality for no enforceable gain. The mitigation is disclosure, not
prevention: the chat UI now tells the user what leaves the machine and asks
them not to share identifying details (implemented in the same change as
this ADR — see `frontend/src/features/chat/Composer.jsx`).

### Cost limits became mandatory

An unmetered hosted call is a cost the local model never had, so a per-user
daily token budget (`llm_usage` table, `src/services/usage.py`) now gates
generation, returning 429 with `Retry-After` once exhausted. Two limits are
already known and accepted rather than fixed:

- one request can overshoot the budget, since the check happens before the
  call and the spend is recorded after it — the budget bounds the *next*
  request, not the one in flight;
- the budget is per-user, so `N` accounts means `N` independent budgets;
  there is no account-wide ceiling.

### Eval floors moved up, measured not assumed

Retrieval is unaffected by this change (unchanged models): routing 25/25,
coverage 20/21 and 20/21 across two corpora, abstentions 4/4. Generation
improved measurably — `scripts/eval_generation.py` answers 7/8 → 8/8,
follow-ups 2/3 → 3/3, refusals held at 4/4 — across three consecutive runs
with identical results, which is what makes full-marks floors safe to
commit as the new baseline (`ffa0b06`).

### Open, recorded not fixed

`_build_user_prompt` (`src/services/generation.py`) still ends its
instruction with "Think step by step.", written for a model that did not
reason natively. `gpt-5-mini` reasons in separate, already-billed tokens, so
that instruction now leaks step-by-step framing into the visible answer
(e.g. "Step 1 — definition and payment:"). Left as-is for this iteration;
fixing it needs its own change plus a floor re-measure, since it changes
generated text shape.
