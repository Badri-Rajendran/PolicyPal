# 0021 — The BM25 index lives in the database, not on local disk

## Status

Accepted. Amends ADR 0004's hybrid retrieval, which put the sparse index in
`data/corpus/indices/bm25.pkl`.

## Context

Hybrid retrieval (ADR 0004) needs a BM25 index at request time.
`_bm25_index()` read it from a pickle on local disk, cached per process, and
raised `FileNotFoundError` if it was absent.

Nothing caught that exception. The chat route's catch-all turns it into a 500,
so **a deployment without the file answers no questions at all** — not
degraded, not sparse-only: every question fails.

That never showed up because the app had only ever run on the machine that
built the corpus. Containerising it makes the gap immediate, and unfixable
where it stands:

- `data/` is gitignored and stays that way, so CI cannot build an image
  containing the file;
- the index is built by `make ingest`, which is a local, long-running job;
- the file is small (3.4 MB), but the constraint is provenance, not size.

The alternatives were object storage — a storage account, a credential, an SDK
and a new startup failure mode — or building the image locally, which is not
CD at all.

Meanwhile the index is **derived data**: everything it contains comes from the
`chunks` table, which already holds each chunk's text and id.

## Decision

### One row, in the database that holds the chunks it indexes

`search_indexes` — `name` (primary key), `payload`, `chunks`, `built_at`. The
BM25 index is the only row today; a second index would be a second row, not a
second table.

- **The request path reads it from Postgres**, still cached per process with
  `lru_cache`, so the cost is one query per worker.
- **A missing index raises `MissingSearchIndexError`** naming the command to
  run, instead of a `FileNotFoundError` naming a path that will not exist in
  the environment that hit it.
- **Nothing writes to local disk.** `bm25_index_path` and `INDEX_DIR` are
  gone; there is no path to configure.

### It is rebuilt from the chunks, not restored with them

`make build-index` reads `chunks` and rebuilds the index: no fetching, no
chunking, no embedding. `make ingest` still builds it as the last step of a
full run.

This is what makes seeding a fresh database one restore plus one command, and
it means the index can never be silently out of date with a corpus that was
loaded some other way.

### The payload no longer carries a second copy of the corpus

The pickle held `{"bm25", "chunk_ids", "texts"}`. `texts` was read by nothing
outside a test: retrieval uses `bm25` and `chunk_ids`, and the text itself is
a column away in the table being indexed. Dropping it took the payload from
3.4 MB to 1.8 MB for the same 1,568 chunks.

### Unpickling stays, and why that is not a new risk

The payload is a pickle because `BM25Okapi` is a Python object. It is written
only by this project's own ingestion, into a table only this application
writes to, and it was already being unpickled from a file. Moving the bytes
from a file the app owns to a row the app owns does not add a source of
untrusted input. Anyone who can write that row can already run code as the
application.

If that changes — a shared database, or a second writer — this is the thing to
revisit, and the answer is a schema-validated format rather than tighter
permissions.

## Consequences

- **The app runs where there is no `data/` directory.** This is the change
  that makes a container work, and it is testable: a container with no `data/`
  answering a question is the proof.
- **One more thing in the database dump,** and one fewer thing to copy beside
  it.
- **A re-chunk must be followed by an index build,** as before — but now the
  two are in the same database, so `built_at` and `chunks` say when the index
  was made and from how many, which a file's mtime did not.
- **`make ingest` now needs a database.** It always did, at the embed stage;
  the chunk stage no longer stands alone.
