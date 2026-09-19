# 0013 — Plan documents: the SBC, fetched politely, stored as text

## Status

Accepted. Phase 2, first half: ingestion. Retrieval over these documents is
ADR 0014. Amended by ADR 0015: a document is parsed once per parser version,
not on every run, and its PDF is deleted once its text is stored.

## Context

The plan catalog (ADR 0009) answers what a plan costs. It cannot answer what a
plan covers: "does it cover MRIs?", "what's excluded?", "what's the ER copay?".
Those answers are in plan documents, and only one kind is obtainable before
purchase.

- **The Evidence of Coverage (EOC) is usually not.** Most insurers provide it
  only to paying members. It is also 100–200 pages of bespoke contract per
  issuer.
- **The Summary of Benefits and Coverage (SBC) is.** It is federally required,
  must be given to anyone shopping, and follows one standard template of about
  8 pages. It includes exclusions, cost sharing for each common medical event,
  and three worked coverage examples.

The catalog already stores each plan's SBC link as `plans.benefits_url`
(docs/findings/cms-marketplace-api.md). A spike against real links, on
2026-09-19, found:

- **Direct links.** 4 of the 5 issuer hosts in the loaded Texas catalog served
  the PDF directly.
- **One refusal.** UnitedHealthcare's CDN answered every automated request with
  a 403, including one for its `robots.txt`.
- **Shared documents.** Several plans can share one document: the 89 loaded
  Texas plans point at 70 URLs.

The repository is public, and ADR 0003 has already turned down one source,
state insurance department guides, over copyright.

## Decision

### The SBC is the plan document

It is what a shopper can get, and its fixed headings make chunking
structure-aware:

- a chunk is one of the template's sections;
- its heading is metadata that means the same thing for every issuer;
- nothing is split by length unless a section overruns the chunk size.

EOCs are out of scope.

### How it is fetched

`make ingest-sbc STATES=…` reads the SBC behind each distinct `benefits_url`
among the catalog plans of those states.

- **Only public HTTPS hosts.** A URL that is not HTTPS, or names an IP address
  or a local host, is refused before any request. The check runs again on
  every redirect, which is followed by hand rather than by `requests`.
- **Refusals are respected.**
  - `robots.txt` is read and obeyed, using the standard library's parser.
  - A 401 or 403, on the file or on `robots.txt`, records the document as
    `blocked`. A refused `robots.txt` counts as disallowing everything.
  - Nothing tries to get around a refusal: no browser user agent, no other
    route to the file. Those plans get no SBC answers; answers link their PDF
    instead.
- **Polite:**
  - two seconds between requests to one host;
  - a timeout;
  - the file is streamed and abandoned past 15 MB;
  - the response must start like a PDF.
- **Downloaded once.** The file is cached under the gitignored `data/sbc/raw/`
  and written atomically. A re-run reads the cache and makes no request for
  it; only documents that failed are requested again.
- **Every attempt is recorded** in `sbc_documents`: `ok`, `blocked`,
  `http_error`, `not_pdf`, `too_large`, `wrong_year` or `unparseable`, with a
  reason of a few words. A failure is retried on the next run, and the run
  ends by naming the plans left without an SBC.

### The plan year is part of a document's identity

Issuers reuse one URL every year with new contents. So:

- `sbc_documents` is unique on `(url, plan_year)`, not on the URL alone.
- A plan reaches its document through its own `benefits_url` and
  `plan_year`, with no foreign key: plan re-syncs stay unaware of documents.
- A document whose "Coverage Period" is for another year is stored as
  `wrong_year`, gets no chunks, and has its cached copy discarded, so a
  corrected file at the same URL is fetched again.

### Stored as text, apart from the corpus

Chunks go in `sbc_chunks`, not `chunks`. `make ingest` rebuilds `chunks`
wholesale and never touches SBC text. SBC ingestion is incremental:

- each document is one transaction that replaces that document's chunks;
- a document that fails on a later run loses its chunks, so no answer quotes
  an SBC that is no longer the plan's;
- every run re-parses from the cache, so a parser fix reaches every document
  without a new download.

Why a separate table, and why no embeddings: ADR 0014.

### Copyright and redistribution

The SBC is a government-mandated, standardized disclosure that issuers must
give to anyone considering the plan. Its copyright claim is materially weaker
than a bespoke contract's, but not zero. PolicyPal therefore:

- **stores the extracted text** in its own database, for retrieval;
- **quotes it briefly**, in answers that cite the plan and point to the
  issuer's own PDF for the full document;
- **never redistributes a file.** PDFs are cached locally only to avoid
  downloading them again. They are never served, never re-hosted and never
  committed.
- **commits no issuer document or excerpt**, because the repository is public.
  Parser tests use hand-written pages in the template's shape. Real documents
  are checked in the live ingest, and the counts are recorded in
  docs/findings/sbc-documents.md.

**This departs from ADR 0003's bar, deliberately.** ADR 0003 admitted only
public-domain text: it turned down NAIC's guides for having "no clear reuse
license", and California's guides for their copyright notice. SBCs have no
reuse license either. The departure is accepted because:

- **There is no public-domain alternative for plan-specific coverage.** Every
  other source describes coverage in general.
- **The document is a mandated disclosure** that issuers must hand to anyone
  shopping, which is exactly the use here.
- **The use is narrower than the corpus's.** Nothing is redistributed as a
  file, passages are quoted only to answer about that plan, and each answer
  points to the issuer's original.

The README's "educational and portfolio" framing is context, not the
justification. If an issuer objects, its documents can be removed by deleting
its `sbc_documents` rows, which cascades to their chunks.

### How a PDF becomes sections

- **pdfplumber** (MIT) is the PDF library. It is pinned in `uv.lock` and
  scanned by `pip-audit` with the rest; pdfminer.six resolves to 20260107,
  with no known vulnerabilities.
- **pdfplumber sits behind `read_pdf`,** and nothing else touches it.
  - The template is found by its headings. Table rows are read by their
    left-column cell: a merged "If you…" cell spans its whole group.
  - Characters are selected by their midpoint, because cropping clips them
    and interleaves neighbouring lines.
  - More than 30 pages is refused as not an SBC.
- **The parse** yields:
  - one section per "Important Questions" row;
  - one per medical-event group, rejoined across page breaks;
  - the exclusions and other covered services;
  - the rights, appeals and minimum-coverage notes;
  - the three coverage examples.

## Consequences

- **Plans whose issuer refuses automated access have no SBC answers.** In the
  first live run that is UnitedHealthcare (TX) and Anthem (NH), whose hosts
  refuse even `robots.txt`: 26 of 156 documents. Answers for those plans link
  the PDF. The counts are in docs/findings/sbc-documents.md.
- **The parser is tuned to the template, not to any one issuer.** A layout
  that defeats it fails as `unparseable` or yields fewer sections, and the
  live run's per-issuer counts are where that shows.
- **`make ingest-sbc` depends on `make ingest-plans`** for the same states and
  year. It exits with instructions when the catalog is empty.
- **pdfplumber brings in pdfminer.six, pypdfium2 and Pillow.** All three parse
  untrusted files, which is why the size cap, the page cap and the
  `%PDF` check exist.
