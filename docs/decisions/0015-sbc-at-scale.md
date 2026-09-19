# 0015 — SBC at scale: the largest issuers, parsed once, PDFs not kept

## Status

Accepted. Phase 3. Amends ADR 0013 where it says documents are "downloaded
once" and "every run re-parses from the cache". **Its "PDFs are deleted once
their text is stored" is superseded by ADR 0016:** every downloaded SBC is
kept.

## Context

Phase 2 stored the SBCs of NH, DE and two Texas counties: 130 documents, with
26 more blocked. Phase 3 (docs/plans/phase-3-sbc-top-issuers.md) extends this
to the largest issuers in FL, TX, NC, TN, AL and SC, where the count grows
into the thousands. Measured before deciding:

- **Parsing takes 1.45 s per document**, averaged over 15 cached PDFs. ADR 0013
  re-parses every cached PDF on every run, so a few thousand documents would
  take hours per run even when nothing has changed.
- **A PDF averages about 0.9 MB** (121 MB for 130). A cache that is never
  emptied grows to gigabytes.
- **The Marketplace API has no enrollment figures**, so "largest" needs another
  source. CMS's
  [Issuer Level Enrollment PUF](https://www.cms.gov/marketplace/resources/data/issuer-level-enrollment-data)
  gives average monthly enrollment per HIOS issuer, with no names, for 2025 at
  the newest. The 2026 names come from the API's `GET /issuers`.

The roadmap's concerns about retrieval at scale no longer apply. They were
written before ADR 0014:

- SBC text lives in `sbc_chunks`, without embeddings;
- general search never reads it;
- a coverage question reranks one plan's ~25 sections.

The corpus stays at 1,568 chunks however many SBCs are stored. So nothing here
touches BM25/dense `top_k`, the 0.5 gate or an HNSW index.

## Decision

### The largest issuers are parent companies, listed in the repo

`src/ingestion/sbc/top_issuers.py` lists the ten largest parent companies by
2025 average monthly enrollment in the 30 HealthCare.gov states. Each is
listed with the HIOS issuer IDs it sells under.

| Parent | 2025 enrollment | Share |
| --- | --- | --- |
| Centene (Ambetter) | 4,355,554 | 29.3% |
| Oscar Health | 1,694,116 | 11.4% |
| UnitedHealth Group | 1,251,407 | 8.4% |
| Health Care Service Corporation (BCBS TX, OK, MT) | 1,184,678 | 8.0% |
| Florida Blue | 1,125,665 | 7.6% |
| Molina Healthcare | 460,305 | 3.1% |
| Elevance Health (Anthem, Wellpoint) | 394,585 | 2.7% |
| Blue Cross and Blue Shield of North Carolina | 369,398 | 2.5% |
| BlueCross BlueShield of South Carolina | 263,668 | 1.8% |
| Select Health | 262,614 | 1.8% |

- **Together they are 76.6%** of the 14.8 million enrollees in those states.
- **Aetna, sixth with 4.7%, is left out**: it withdrew from the marketplace for
  2026.
- **Blocked parents stay in the list.** UnitedHealthcare and Anthem already
  refuse automated access (ADR 0013). They are recorded as blocked and linked,
  never worked around.
- **The list is checked in, not discovered.** A parent is a business fact the
  catalog does not carry, so each issuer was assigned by its name and checked
  by hand.
- **Only the derived IDs are committed**, not the spreadsheet.
- **IDs first seen in 2026 are added from the catalog.** A parent can sell
  under a new HIOS ID, which 2025 data cannot show. After a state's catalog is
  loaded, its issuers are compared with the list by name, and a match joins its
  parent, marked with its year.
- `make ingest-sbc TOP_ISSUERS=1` reads only these issuers' plans, and
  `ISSUERS=40788,66252` only the IDs given. That second form is how Phase 2's
  other Texas issuers stay current. Without either, every plan in the states
  is read, as in Phase 2.

### A document is parsed once per parser version

- `sbc_documents.parser_version` records which parser produced a document's
  chunks. It is NULL for anything but `ok`.
- A run skips every `ok` document already stored at the current
  `PARSER_VERSION` (`src/ingestion/sbc/extract.py`): no request, no parse.
- **Bumping the version is how a parser fix reaches stored documents.** This
  replaces ADR 0013's "every run re-parses from the cache".
- Failures are still retried on every run, as before.

### PDFs are deleted once their text is stored (superseded by ADR 0016)

- The PDF is deleted after the document's text is committed. If the write
  fails, the file stays.
- **`--keep-pdfs` (`KEEP_PDFS=1`) keeps them** for tuning the parser. It also
  keeps unparseable files, which are the ones tuning needs.
- **The next run without it removes them.** It skips the documents already
  current, and deletes their kept PDFs as it does, with no request.
- A `wrong_year` file is always deleted, as ADR 0013 requires.

**This strengthens ADR 0013's copyright position.** PolicyPal no longer holds
issuers' files at all, only the extracted text it quotes from.

**The cost:** a parser version bump downloads every stored document again,
paced at two seconds per host. So parser work happens during a tuning pass
with `--keep-pdfs`, before the run that deletes the files.

## Consequences

- **A run with nothing new is cheap.** It is one query, plus a retry of
  whatever failed.
- **Parser fixes cost downloads once PDFs are gone.** Tune with
  `KEEP_PDFS=1` first.
- **Known limits, left to Phase 4 (maintenance and refresh):**
  - `fetched_at` is also stamped when a kept PDF is reused, so it is not a
    reliable download time.
  - A document whose plans moved to a new URL stays as an orphan row. Answers
    never reach it, because they look documents up by the plan's current URL.
  - A file the issuer replaces at the same URL goes unnoticed until the parser
    version changes.
  - `wrong_year` and `http_error` documents are downloaded again on every run.
- **The ranking ages.** Revisit it once CMS publishes 2026 enrollment by issuer.
