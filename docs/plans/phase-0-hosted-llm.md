# Phase 0 — swap the local LLM for a hosted one

**Status:** complete — shipped in PR #9; decision recorded in [ADR 0008](../decisions/0008-hosted-llm.md)
**Depends on:** nothing
**Blocks:** Phase 1

## Goal

Replace `Qwen/Qwen2.5-0.5B-Instruct` with a hosted OpenAI model, so that
tool-calling becomes reliable enough to build plan comparison on.

Ship this green — all tests passing, eval floors re-measured — *before* Phase 1
begins. If abstention or answer quality regresses later, that ordering makes it
unambiguous whether the model or the feature caused it.

## Why

Tool-calling is what makes Phase 1's architecture possible, and a 0.5B model
handles it poorly: malformed arguments and missed calls. Upgrading the local
model is not an option — the 1.5B variant *"exceeded available RAM and thrashed
swap"*, which is why the project is on 0.5B at all.

## What moves, and what does not

**Only the LLM.** `BAAI/bge-small-en-v1.5` embeddings and the
`cross-encoder/ms-marco-MiniLM-L-6-v2` reranker stay local, so ingestion and
retrieval remain free, offline, and unaffected by this change.

That matters for the eval story below: retrieval evals stay valid, generation
evals do not.

## Code

### `src/services/generation.py`

`_llm()` (line 80) is the single seam. It is called from exactly one site
(line 115, inside `_generate`). Replace the `(tokenizer, model, device)`
triple with an OpenAI client.

- `answer()` and `rewrite_query()` route through `chat.completions.create`
- **Keep `_neutralize_delimiters` and the trust-boundary `SYSTEM_PROMPT`
  exactly as they are.** OWASP LLM01 prompt-injection defence is not
  model-specific, and a hosted model is not less susceptible
- Do not remove device selection — embeddings and the reranker still use it
- `torch` and `transformers` imports leave this module but stay in the project

### `src/policypal/config.py`

Add:

| Setting | Purpose |
| --- | --- |
| `openai_model` | Model identifier |
| `openai_api_key` | Env-sourced, never defaulted in code |
| `llm_max_output_tokens` | Replaces `max_new_tokens` |
| `llm_request_timeout` | Hosted calls can hang; local ones could not |
| `llm_daily_token_budget` | Cost ceiling, see Security |

Retire `llm_model_revision` — pinning a HuggingFace commit is meaningless for
a hosted model. Note in the ADR that this weakens the CWE-494 posture the
pinned revisions provided: model behaviour can now change under us without a
version bump.

Keep `temperature` (currently 0.2).

## Tests

`tests/test_generation.py` has **20 `_llm` mock points**. This is the bulk of
the phase — the fixture shape changes wholesale, not just the patch target.

| Now | Becomes |
| --- | --- |
| `_FakeBatchEncoding` dict/attr hybrid | Not needed |
| `tokenizer.apply_chat_template` | Assert on the `messages` list passed to the API |
| `model.generate` returning tensors | Fake `client.chat.completions.create` |
| `tokenizer.decode` | `.choices[0].message.content` |
| — | `.choices[0].message.tool_calls`, new in Phase 1 |

Tests whose *intent* must survive the rewrite unchanged:

- `test_fallback_does_not_load_the_model` — now proves no paid API call is
  made when there is nothing to answer. More valuable than before, not less
- every `_build_user_prompt` delimiter-injection test — these assert on prompt
  construction, which does not change
- `test_rewrite_neutralizes_delimiters_in_stored_history`
- `test_answer_places_history_between_the_system_prompt_and_the_question`

**No test may make a real API call.** CI has no key and must never need one.

## Eval floors must be re-measured, not carried over

[ADR 0004](../decisions/0004-retrieval-tuning.md) built `ABSTENTION_SET` and
the coverage floors against Qwen, and already records that abstention
*"is not reliable across the board"* — naming specific questions that leak
through. A different model has different abstention behaviour, so those
numbers describe a system that no longer exists.

1. `scripts/eval_retrieval.py` — unaffected, retrieval stays local. Run it to
   confirm that claim rather than assuming it
2. `scripts/eval_generation.py` — re-run and reset floors to the new measured
   baseline. Record both the old and new numbers in the ADR
3. Re-verify each `ABSTENTION_SET` question individually. A question that
   abstained under Qwen may now get answered, which is a regression in the
   safety property even if the answer reads well

Every eval run now costs money — `eval_generation.py` generates once per
question. Note the per-run cost in the README so it is a deliberate choice.

## Security

- `OPENAI_API_KEY` lives in `.env` only. **Never `git add` or `git commit` a
  `.env` file, in any case or situation** (CLAUDE.md). Confirm `git diff
  --stat` before every commit in this phase
- Add the variable to the README environment table
- **Cost limiting is now a CLAUDE.md requirement**, not a nicety: *"enforce
  rate/cost limits."* Flask-Limiter caps requests, not spend. A prompt
  designed to trigger long generations is now a billing event. Add a per-user
  token budget enforced before the call
- **PII egress becomes real.** Under Phase 1, a user typing "silver plans in
  60601, I'm 34" sends that ZIP and age to a third party in the raw message —
  before any tool call exists to structure it. CLAUDE.md says keep PII out of
  prompts. Decide explicitly in the ADR: accept it and document it, or redact
  before sending. Do not let it happen by default
- Keep API keys and PII out of logs. The existing `logger.info` calls log
  lengths and counts, not content — preserve that discipline

## ADR 0008 — hosted LLM

No existing ADR covers the local model choice; it appears only as a changelog
line. Nothing is superseded, but reversing local-only inference is the most
material architectural decision in the project so far, and CLAUDE.md requires
recording material choices.

Cover: why tool-calling forces it, what stays local and why, PII egress,
cost controls, the loss of pinned-revision reproducibility, and the eval
invalidation with before/after numbers.

## Verification

```bash
uv run pytest                              # green, including 20 rewritten mocks
uv run ruff check .                        # no new lint
uv run python -m scripts.eval_retrieval    # unchanged floors, retrieval is local
uv run python -m scripts.eval_generation   # re-measure, then reset floors
git diff --stat                            # .env must not appear
```

Manual: ask a definitional question end-to-end and confirm the answer still
cites sources; ask an `ABSTENTION_SET` question and confirm it still declines.

## Out of scope

- Any Marketplace API or plan work — that is Phase 1
- Swapping the embedding model or reranker — they stay local
- Streaming responses
- Removing `torch`/`transformers` from the project
