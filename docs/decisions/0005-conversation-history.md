# 0005 — Conversation history: making follow-up questions work

## Status

Accepted

## Context

`threads` and `messages` have existed since the API landed (ADR 0001). The UI
renders a conversation, the API stores and returns one, and every part of the
product implies that a follow-up question works.

It does not. `create_message` calls `answer_query(body.content)` with the
single newest message, so the model has never seen a prior turn:

```
user: "What is a deductible?"          → grounded answer
user: "What about for auto?"           → no referent at all
```

### Passing history to the prompt does not fix this

The obvious fix — put prior turns in the prompt — fails, and it is worth
recording why, because it looks sufficient:

```python
def answer_query(query, top_k=None):
    chunks = search(query, top_k)          # runs on the bare fragment
    return answer(query, chunks), chunks

def answer(query, chunks):
    if not chunks:
        return NO_ANSWER_RESPONSE          # returns here
```

Retrieval runs first, on `"What about for auto?"` alone. A cross-encoder
scores that fragment against every chunk; nothing clears the 0.5 relevance
gate (ADR 0004), `search()` returns `[]`, and `answer()` short-circuits to
the refusal **before history would ever be read**. History in the prompt only
helps a follow-up that already retrieves well on its own — which is not the
failing case.

The fix has to change what gets *retrieved*, not only what gets *generated*.

## Decision

### Rewrite the follow-up into a standalone question before retrieval

A generation call turns the conversation plus the new message into one
self-contained question, and retrieval runs on that:

```
history + "What about for auto?"
    → "What is a deductible in auto insurance?"
    → retrieve on the rewrite, then answer
```

The alternative considered was rule-based expansion — concatenate the
previous user turn with the current one. It is free and deterministic, and it
would handle the example above. It was rejected because it drags the old
topic along on every turn: after switching from deductibles to flood
insurance, the expanded query still carries "deductible" and pollutes the
candidate set. Rewriting handles a topic change cleanly, which is the
common case in a real conversation.

The cost is real and accepted: **a second generation call**, so a follow-up
takes roughly twice as long as a first message on the local 0.5B model.

Three things bound that cost and its risk:

- **Skipped when there is no history.** A first message — the majority of
  traffic in short sessions — keeps exactly its current latency.
- **Bounded output.** `rewrite_max_new_tokens` is small; the result is
  collapsed to a single line and length-capped before it reaches `search()`.
- **Fails backwards, never closed.** An empty, over-long or malformed rewrite
  falls back to the raw query. The worst case is today's behaviour, never a
  query that retrieves nothing.

### Budget history by tokens, not turn count

`history_token_budget` (1024) is filled newest-first, dropping the oldest
turns that no longer fit. A fixed turn count behaves badly at both extremes:
three long turns can crowd out the retrieved context a small model needs to
stay grounded, while three one-line turns waste an available window.

`count_tokens()` is reused rather than the real tokenizer. It approximates at
1.35× word count, which is already trusted for chunk sizing, where the error
matters more. Against 1024 tokens of a 32,768-token window the slack is
enormous, and the approximation keeps history selection a pure function that
tests without loading a model.

It moves from `src/ingestion/chunking.py` to `src/core/text.py` in the same
change: `services/` importing from `ingestion/` is wrong-direction coupling,
and `core/` is already where shared helpers live.

## Security

History is written by the user and stored verbatim, so it is untrusted input
arriving on a second path (LLM01, as ADR-adjacent to the prompt hardening
already in `generation.py`). Two consequences:

- Every history turn passes through `_neutralize_delimiters()` before it
  enters a prompt, exactly as the question and retrieved context already do.
  Otherwise a stored message could forge a `</user_question>` tag on a *later*
  turn — a stored injection rather than a reflected one.
- The rewrite prompt is a second injection surface, and its output steers
  retrieval. That output is never executed, never shown to the user, and is
  constrained and validated before use; a rewrite that does not look like a
  short question is discarded in favour of the raw query.

## Consequences

Follow-up questions work, which is what the stored conversation has always
implied. Follow-ups cost roughly 2× a first message in latency — acceptable
for a local small model, and the thing to revisit first if generation moves
behind an API where a rewrite call is cheap and parallelisable.

**That move happened (ADR 0008) and this was not revisited.** Generation and
the rewrite both run against `gpt-5-mini`/`gpt-5-nano` now, and the rewrite is
still a serial call before retrieval rather than one issued alongside it. It
stays open, and recorded here rather than implied: the latency is acceptable
in use, so nothing has forced the question, but the reason given for deferring
it no longer holds.

Retrieval quality for follow-ups now depends on a generated artefact, so it
is no longer fully deterministic. `scripts/eval_generation.py` grows a
multi-turn case for exactly that reason; the deterministic parts — history
selection and the rewrite guardrails — stay unit-testable without a model.
