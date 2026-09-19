# 0019 — Keeping SBCs current

## Status

Accepted. Phase 4. Supersedes ADR 0015's "Known limits, left to Phase 4", and
amends ADR 0013's "a failure is retried on the next run" and ADR 0016's
folders.

## Context

Phase 4 is the first phase that does not end. Plan years roll over every
autumn, issuers replace documents mid-season, and links rot. Nothing in the
pipeline could notice:

- **A changed file went unseen.** `fetch_pdf` returns the cached PDF whenever
  one exists, so a document only changed if the parser version did.
- **Every failure was retried on every run.** Ingesting one more state
  re-requested BCBS of North Carolina's 57 challenged links, and every blocked
  host, for nothing.
- **`fetched_at` was stamped on re-parse,** so it could not date a download
  (fixed in ADR 0018).
- **A document whose plans moved to a new link stayed as an orphan row.**

The files must stay on this machine (ADR 0016), so nothing here can run in CI
or in the cloud: a scheduled job elsewhere would mean downloading issuers'
documents somewhere else.

## Decision

### Reading and re-checking are separate commands

**`make ingest-sbc`** reads only:

- documents with no row;
- `ok` or `unparseable` rows stored by an older parser;
- `ok` rows whose PDF has gone missing.

It reports how many recorded failures it skipped, and names the command that
retries them.

**`make refresh-sbc`** does all of that, and asks every stored document
whether it has changed, retrying failures too. It is the only command that
re-requests a document we already have.

This keeps state-by-state ingestion cheap and polite, and puts every
re-request behind one command with one cadence.

### A refresh asks with the issuer's own validators

`revalidate()` sends `If-None-Match` and `If-Modified-Since` with whatever the
issuer served last time, stored in `sbc_documents.etag` and `last_modified`.
A 304 costs the issuer almost nothing. The safety checks are unchanged: HTTPS,
public hosts, `robots.txt`, and two seconds between requests to one host, at
every redirect.

**The reply is compared in memory.** A file is written only when its bytes
differ from the stored hash, so no duplicate is ever written and then removed.

### What a refresh does with what it finds

| Outcome | Row | Text | File |
| --- | --- | --- | --- |
| 304, or the same bytes | `checked_at` stamped | kept | untouched |
| Changed, and it parses | `ok`, new `sha256` | replaced | the old one archived |
| Changed to another year, or unreadable | that status | dropped | the old one archived; the new one to `rejected/` or the cache |
| **Temporary:** 5xx, 429, timeout, network error | unchanged, not even `checked_at` | **kept** | untouched |
| **Lasting:** 404, not a PDF, too large, now refused | that status | dropped | archived |

The temporary/lasting split is the one deliberate departure from ADR 0013's
"a document that fails now loses its chunks". An outage at an issuer is not
evidence about the document; a 404 or a refusal is.

### A replaced file is archived, never deleted

The file a new one replaces moves to
`data/sbc/archive/<year>/<key>-<sha256 prefix>.pdf`. With `raw/` and
`rejected/`, every SBC ever downloaded stays on disk (ADR 0016). There is no
backup: `data/sbc/` is the only copy, by choice.

### Cadence, and the plan year

The runbook is docs/runbooks/sbc.md: a monthly refresh, and the rollover in
late October, when CMS publishes the next year's plans. `make ingest-plans`,
`make ingest-sbc`, `make refresh-sbc` and `make sbc-report` all take
`YEAR=2027`; without it they use the calendar year, which is the wrong one
during open enrollment.

Older years are kept, rows and files: a saved plan card still names the plan
year it showed.

### What is reported, not fixed

`make sbc-report` (Phase 4) names the things this ADR chooses not to act on
automatically:

- documents no plan points at any more, because the plans moved link;
- plans the latest catalog run did not return, which stay searchable;
- documents an older parser stored.

## Consequences

- **A monthly refresh is the only regular network cost,** and issuers that
  send an ETag answer most of it with a 304.
- **An issuer that sends no validator is downloaded in full each month.** The
  bytes are compared and thrown away when they match.
- **A blocked host is asked once a month rather than once a run.**
- **Nothing runs unattended.** A missed month shows up as an old `checked_at`
  in the report, not as an error.
- **Disk grows with every changed document,** by one archived copy each.
