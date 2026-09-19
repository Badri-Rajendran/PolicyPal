# 0007 — Persisting citations

## Status

Accepted. Amended by ADR 0017: an answer that called `plan_coverage`
saves only the corpus sources it cites.

## Context

Citations were returned once and never stored. `POST /messages` answers with
`MessageWithSourcesResponse`, carrying the chunks the answer was grounded in;
`GET /messages` answers with `MessageResponse`, which has no such field, and
nothing in the schema held them. The two endpoints disagreed about what a
message is.

Nobody noticed, because reopening a conversation was not possible: the token
lived in React state, so a reload signed the user out and there was no
restored transcript to be wrong. Session persistence (ADR 0005's sibling
change) made the gap reachable, and browser verification found it
immediately — a reloaded conversation shows every answer with its sources
stripped.

That matters more than a missing field. The product's claim, in the README
and in the empty state, is that PolicyPal "always shows where an answer came
from". An answer without its sources is exactly the ungrounded assertion the
whole retrieval pipeline exists to avoid, and a restored conversation looked
less trustworthy than a live one for no reason the user could see.

## Decision

A `message_sources` table: one row per citation, foreign-keyed to the
message, cascading on delete so citations die with the conversation.

`MessageResponse` gains `sources`, and `MessageWithSourcesResponse` goes away:
with citations on the message itself, the wrapper would have returned them
twice in one payload, leaving two places to read and no answer about which is
authoritative. `POST` and `GET` now return the identical shape.

`MessageItem` already renders `message.sources` when present, so the UI
change is confined to unwrapping the send response.

A JSONB column on `messages` was the alternative, and is the smaller change:
citations are display-only, never filtered or joined. The table was chosen
for the questions it keeps answerable — which sources are cited most, which
are never cited at all, whether a corpus addition earns its place. Those are
retrieval-quality questions this project already asks in its evals, and a
JSONB blob answers them badly.

### `chunk_id` carries no foreign key

This is the part worth recording, because the normalised instinct is to add
one and it would be a mistake.

`make ingest` calls `embed.execute()` with `rebuild=True`, which deletes
every row in `chunks` before reinserting. A foreign key to `chunks.chunk_id`
would therefore either block re-ingestion outright, or — with a cascade —
silently delete every citation ever recorded the next time the corpus was
rebuilt. Conversation history would quietly lose its grounding as a side
effect of a routine ingest.

So `chunk_id` is stored as a plain string: a record of what was cited at the
time of the answer, not a live pointer into a table that is rebuilt on a
schedule. `source` and `relevance` are stored alongside it for the same
reason — the citation has to remain readable after the chunk it names is
gone or has been re-chunked into different boundaries.

## Consequences

A reopened conversation is now identical to a live one, which is what the
persistence work implied and did not deliver.

Listing messages gains a join. It is bounded by thread length and the
`(thread_id, created_at)` index already drives the ordering, so the cost is
small — but message listing is no longer a single-table read, and a very long
thread will feel it first.

Citations are a historical record, deliberately not tied to the current
corpus. A cited chunk can no longer exist, or can have been re-chunked so
that its `chunk_id` refers to different text. The stored `source` and
`relevance` stay accurate about what the answer was actually built from,
which is the honest thing for a citation to record.
