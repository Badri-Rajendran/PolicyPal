# 0027 — Streaming answers, cited passages, and renaming threads

## Status

Accepted. Part of the chat redesign
([spec](../superpowers/specs/2026-09-26-chat-redesign-design.md), section 3).
It amends two earlier ADRs:

- **ADR 0007.** A citation now also stores a SHA-256 of the passage text the
  answer used (`message_sources.content_sha256`), so a passage can be shown
  later only while it still says what was cited.
- **ADR 0022.** An open answer stream holds one of the worker's 8 gthread
  threads for as long as it runs, as a blocking request already did.

Sub-project 3 of the California expansion, which had planned to take this
number, takes ADR 0028 instead.

## Context

The chat worked, but three things made it read like a prototype:

- **Answers arrived all at once**, after 5 to 40 seconds behind a spinner:
  a rewrite, a search, up to two tool rounds and the reply, with nothing shown
  in between.
- **Sources couldn't be read.** A citation was a file name and a match score.
  A user had no way to see the text an answer relied on, and the chunk behind
  a citation can be rebuilt in place by the next ingest (ADR 0007), so its
  text today may not be what was cited.
- **Threads couldn't be renamed.** Every thread kept the first 80 characters
  of its first question.

## Decision

### Streaming: Server-Sent Events over `fetch`

`POST /api/chat/threads/<id>/messages/stream` takes the same body as
`POST …/messages` and answers `200 text/event-stream`, with
`Cache-Control: no-cache` and `X-Accel-Buffering: no`. The browser reads it
with `fetch` and a stream reader: `EventSource` cannot send a POST or a Bearer
header. Each event is `event: <name>\ndata: <json>\n\n`:

| Event | Data | Meaning |
| --- | --- | --- |
| `user_message` | `{message}` | The saved question |
| `stage` | `{stage}`: `understanding`, `searching`, `plans`, `coverage` or `writing` | Progress |
| `notice` | `{text}` | A server-written notice (ADR 0024, 0026), sent as soon as a tool returns it |
| `delta` | `{text}` | Answer text to append |
| `reset` | `{}` | Discard the deltas so far |
| `done` | `{message, thread}` | The saved answer: authoritative, and the client renders it |
| `error` | `{error: "generation failed"}` | The model failed. The question stays and nothing else is saved |

Every event and field is built by server code. The model supplies only the
text of a `delta`, which is the text `done` then carries; the client renders
it as Markdown without raw HTML.

**Generation is one loop with two completion calls.** `answer_events` yields
`Stage`, `Notice`, `Delta` and `Reset` as they happen and ends with
`Done(answer)`. `answer()` drains it, so the CLI, the evals and the JSON route
are unchanged. Blocking and streaming share the tool loop, the fallbacks, the
coverage-citation filter and the notices; only the model call differs.

**Text streams only once the answer is grounded,** meaning chunks were
retrieved or a tool has run. Before that it is held back, so the "no chunks
and no search" refusal (ADR 0010) never has to take back text already shown.
A round that streamed text and then called a tool is followed by `reset`.

**Every check that can fail comes before the stream,** so its error is an
ordinary response: 401, 404 for ownership, 422 for the body, and 429 for the
limiter or the daily token budget. The question is then committed, so no
transaction is open while the model writes. After `Done` the answer is saved
through the same helper as the JSON route (`_save_answer`) and committed, and
only then is `done` sent. `done` always carries exactly what was saved.

**Spend is recorded exactly once, in every ending:** with the answer, on a
model error, and in a `finally` that also runs when the client goes away
(`GeneratorExit`). A client that goes away also closes the model's stream, so
the model stops writing. No partial answer is saved.

**Both send routes share one limit,** `limiter.shared_limit("15 per minute",
scope="chat_send")`, so a user can't double their rate by using both.

### Passages: by citation id, briefly quoted

`GET /api/chat/sources/<source_id>` (60 per minute) returns one of the
current user's citations as it can be shown now.

- **Addressed by the citation's own id,** joined through its message to a
  thread the user owns. Anything else, or a malformed id, is a 404, never a
  403. Chunk ids are guessable, so there is deliberately no lookup by chunk id.
- **Status, from the stored hash:**

  | `status` | When | `quote` |
  | --- | --- | --- |
  | `ok` | The hash matches the text now | the excerpt |
  | `unverified` | No hash (an answer from before this ADR), and the chunk exists | the excerpt; the UI says it may have changed |
  | `changed` | The hash doesn't match | `null` |
  | `missing` | The chunk is gone | `null` |

- **Brief quotes.** At most 300 characters, taken from the part of the passage
  most like the answer, not its first 300 characters: segments are scored by
  the distinct words they share with the answer, and the best one and those
  after it are kept while they fit. `… ` and ` …` mark what was left out. SBC
  text stays within ADR 0013's "quote briefly", and the endpoint never returns
  a passage whole unless it is that short.
- **Credit and links, all derived by the server.** An SBC shows its plan,
  plan year, section and document link. A Wikipedia passage carries its
  CC BY-SA 4.0 credit, read from the source registry's `wikipedia` entry
  (ADR 0025), and a link to the article. HealthCare.gov text is public domain,
  and its page URLs are not stored. A link is returned only if it is `https`
  and passes the ingestion's `unsafe_reason` check (now `src/core/urls.py`),
  so an IP address or a non-public host is never handed to a browser.

### Renaming leaves `updated_at` alone

`PATCH /api/chat/threads/<id>` (30 per minute) sets a title of 1 to 200
characters, after trimming. `updated_at` means the thread's last activity and
orders the list, so a rename must not move a thread to the top. The update
sets `updated_at` to itself, which stops the column's `onupdate` from firing.

## Consequences

- **The JSON route stays.** Scripts and tests use it, and it is the fallback.
  The frontend moves to the stream.
- **Gunicorn's threads bound concurrent streams.** One worker with 8 threads
  (ADR 0022) serves at most 8 answers at once, streamed or not. More needs
  more threads, or a shared limiter backend and more workers. With threads,
  gunicorn runs the gthread worker, whose `--timeout` is a worker heartbeat,
  not a per-request limit, so a long stream is not killed at 120 s.
- **Azure's ingress timeout (about 240 s) is above the usual worst case.**
  That is a rewrite and three answer rounds of up to 30 s each. With every
  call also retried once (`llm_max_retries = 1`), the theoretical bound comes
  close to it. A stream cut there ends like a client that went away: the spend
  is recorded, no answer is saved, and the client shows an error.
- **A stopped or cut stream saves no answer,** only the question, as a failed
  answer already did. The model's usage arrives in the stream's last chunk. A
  round cut short never gets it, so it is counted by estimate, set high: the
  whole prompt plus the output cap. Otherwise ending streams early would spend
  past the daily budget (OWASP LLM10).
- **Citations saved before this ADR are `unverified`,** never shown as if
  checked.
- **The Wikipedia link is built from the stored label,** whose title was
  sanitised at ingest (`Workers'_compensation` became
  `Workers_compensation`). It relies on Wikipedia's redirects for such titles.
