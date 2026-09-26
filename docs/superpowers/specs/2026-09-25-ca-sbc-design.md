# California SBC documents — design (sub-project 2)

**Branch:** `feature_ca_sbc` · **ADR:** 0026 · **Master plan:** the California expansion, SP2.

## Problem

Every California plan loaded from the CMS PUF (ADR 0024) has `benefits_url`
NULL, because the PUF's SBC column is empty. So every California coverage
question ends in "no Summary of Benefits and Coverage link is listed for this
plan". The SBC pipeline (ADR 0013, 0015, 0019) can't help as it stands:

- it accepts only the 30 HealthCare.gov states;
- it reads only `benefits_url`;
- it has no way to take a PDF a person downloaded.

## What was verified (2026-09-25)

| Carrier (HIOS) | CA plans | What the site gives | `robots.txt` for our agent |
| --- | ---: | --- | --- |
| Kaiser (40513) | 7 | SBCs named by HIOS variant, e.g. `…/2026/40513CA0380003-01-en-2026.pdf`. The listing page needs cookies; the PDFs don't. | allowed |
| Blue Shield (70285) | 60 | The broker page's PDFs are California "Summary of Benefits" (part of the EOC), **not** the federal SBC. The parser rejects them. Federal SBCs are elsewhere, still to be located. | allowed (`*/download(s)/` refused) |
| Health Net (67138) | 61 | SBCs only behind a POST search form. | allowed |
| IEHP (51396) | 5 | Static PDFs named by metal level. | allows everything |
| Anthem (27603) | 11 | — | `Disallow: /*.pdf$` |
| L.A. Care (92815) | 5 | — | names AI crawlers (anthropic-ai, ClaudeBot, …); `*` is allowed |
| Sharp (92499) | 9 | — | `Disallow: /docs/default-source/pdfs/` |
| Valley (84014) | 5 | — | 403 |
| Molina, WHA, CCHP (18126, 93689, 47579) | 5, 10, 12 | To be located | allowed |

- **A Kaiser SBC parses cleanly** with the current parser: coverage year 2026,
  25 sections, nothing missing. Its printed title is "Covered CA_Silver 70 HMO".
- **Blue Shield's 18 regional "Trio HMO" filings share one marketing name** per
  metal, so many plan IDs can point at one document. The model already allows
  that: documents are unique on (url, plan_year).

## Decisions (user, 2026-09-25, plus the master plan)

1. **A hand-built, committed manifest**, with a check command. The HTML
   "proposal helper" is dropped: most carriers' pages don't suit it.
2. **A new registry status, `mandated_disclosure`,** which gates California only.
   The 18-state crawl is unchanged; gating it too is a follow-up.
3. **Health Net stays unlinked.** Its plans keep "no link" and point to Covered
   California.
4. **Manual import is allowed for refusing hosts** (earlier decision):
   Anthem, Sharp, Valley, and L.A. Care. L.A. Care is manual-only, because it
   names AI crawlers, which we take as its intent.
5. **Base-plan SBC only.** Answers say so for CSR and AI/AN versions. Per-variant
   SBCs are a follow-up.
6. **Website Terms govern (user, 2026-09-26).** Each carrier's Terms of Use were
   read after this spec was first approved.
   - A carrier whose Terms ban robots or scrapers is manual-only, even where
     `robots.txt` allows us: Kaiser, Blue Shield, Western Health Advantage,
     Anthem and L.A. Care. Valley is manual-only too, because its host blocks
     bots.
   - IEHP, Molina, Balance by CCHP and Sharp are crawled. Sharp's SBC folder
     isn't under its disallowed path, so decision 4's "Sharp manual" is replaced.

   The evidence is in `docs/findings/ca-sbc.md`, and the rule is ADR 0026's.

## Design

### 1. Registry (`src/ingestion/sources/`)

- **New status.** `PERMISSIONS` and `APPROVED` gain `mandated_disclosure`. It is
  valid only for `kind = "sbc_host"`, and its `commercial_use` must be `review`.
  Validation enforces both.
- **New lookup.** `sbc_host_for(url) -> RegisteredSource | None` returns the
  `sbc_host` entry whose `scope_urls` prefix matches the URL. The longest prefix
  wins, and it ignores the `enabled` flag.
- **Scope URLs are `https://host/…` prefixes** (added after review), so a
  prefix can never also match a look-alike host.
- **New entries in `registry.toml`,** one `sbc_<carrier>` per California carrier
  whose SBCs we use:
  - `jurisdiction = "CA"`;
  - `scope_urls` as exact path prefixes;
  - `access` of `crawl` or `manual`;
  - the `robots` outcome with its check date.
- **Health Net** is recorded disabled, with the reason: SBCs only behind a
  search form.

### 2. Manifest (`src/ingestion/sbc/manifests/ca-<year>.csv`, `src/ingestion/sbc/manifest.py`)

- **Columns:** `hios_plan_id,plan_year,sbc_url,verified_on,note`. It holds
  public URLs and IDs only.
- **`load_manifest(path, year)`** checks the file on its own, with no database:
  - the header;
  - the ID matches `^\d{5}CA\d{7}$`;
  - the year equals the file's year;
  - the URL passes `fetch.unsafe_reason` and has a registered `sbc_host` entry;
  - no plan appears twice.

  Any failure raises `ManifestError` naming the line.
- **`apply_manifest(session, rows, year) -> ApplyReport`** makes the manifest
  authoritative for California:
  - It sets `benefits_url` on every `catalog_source = 'ca_sbe_puf'` plan of the
    year. A plan gets its row's URL when that row's host entry is enabled, and
    NULL otherwise.
  - A manifest plan that isn't loaded raises.
  - It reports: linked plans, plans with no row, rows skipped because their host
    is disabled, and distinct documents.

  Disabling a carrier and re-applying is the removal path. PDFs are kept (ADR 0016).
- **Where it runs:**
  - `make apply-sbc-manifest YEAR=` runs it.
  - `make ingest-ca-plans` also runs it after a load when the year's manifest
    exists. If the manifest has an error, the plans stay loaded, and the command
    says the links weren't applied and exits non-zero.
- **`make check-sbc-manifest YEAR=`** only reads. After the ingest it lists:
  - each California document whose printed title doesn't contain every word of
    the plan's marketing name, for a person to judge;
  - rows still unread, split into awaiting manual import and failed with status;
  - plans with no link.

  This is the "verify" step. robots, PDF, parse and coverage year are already
  checked by the ingest.

### 3. Crawl (`ingest.py`, `report.py`, `plans.resolve_states`)

- **California becomes a valid state.** `resolve_states(raw, allowed=MARKETPLACE_STATES)`
  gains a parameter. The SBC ingest and report pass `CATALOG_STATES`, so
  `make ingest-sbc STATES=CA` works; `ALL` stays the 30 API states.
- **California URLs are gated.** For a plan in `FILED_RATE_STATES`, the URL is
  fetched only when its host entry is enabled with `access = "crawl"`. A
  `manual` entry's documents are never requested; they are counted as "awaiting
  `make import-sbc`". The check runs in `ingest.execute`, where every
  California fetch starts, so a mis-applied link can't slip through.
- **Everything else is reused unchanged:** fetch (robots, pacing, redirects,
  PDF check), parse, `wrong_year`, archive.

### 4. Manual import (`src/ingestion/sbc/import_pdf.py`, `make import-sbc`)

- **Invocation:** `make import-sbc YEAR= FILE=path URL=sbc_url`, or
  `make import-sbc YEAR= DIR=folder`. `DIR` matches each file to the one
  manual-access link whose URL basename equals the file name.
- **Checks, before anything is written:**
  - the URL is a `benefits_url` of a plan in that year;
  - its host entry is enabled;
  - the file starts with `%PDF-` within 1 KB (`looks_like_pdf`, split out of `fetch._read`);
  - the file is at most `MAX_BYTES`.
- **Then:**
  1. Archive any cached file with a different hash (`ingest.archive`).
  2. Copy the file to `cache_path(url, year)` with `fetch.save`. The user's file
     is left where it is.
  3. Call `ingest_document(url, year, stored, acquisition="manual")`.
     `fetch_pdf` serves the cached copy, so no request is made.

### 5. Provenance (migration + model)

- **New column.** `sbc_documents.acquisition`: String(8), NOT NULL,
  server_default `'crawl'`, check `IN ('crawl','manual')`.
- **`_store` writes it only when given,** so a re-parse keeps `manual`.
- **A manual document is never re-requested:**
  - `refresh-sbc` skips it and counts it.
  - `ingest-sbc` re-parses it from disk after a parser bump.
  - If its file is missing, the ingest reports "re-import" instead of fetching.
- **`sbc-report`** shows crawled and manual counts. `check-sbc-manifest` lists
  the plans awaiting import.

### 6. Answers

- **A server-written notice on California answers.** When `plan_coverage`
  quotes a filed-rate state's plan, the answer opens with: "Summaries of
  Benefits and Coverage quoted here for Covered California plans are for each
  plan's standard version; people who qualify for cost-sharing reductions or
  American Indian and Alaska Native cost sharing pay less than they show."
- **It is written by the server, not left to the model.** This is the same
  lesson as the prior-year notice. The implementation first put a `note` in the
  tool result and a prompt line asking the model to say it; in a live question
  the model left it out, so it now uses `ToolOutcome.notice`.
- **API-state plans are unchanged.** What their `benefits_url` points to hasn't
  been checked, so nothing is claimed about it.

### 7. Docs

- **ADR 0026:** the manifest, manual import, `mandated_disclosure`, California
  gating. It amends:
  - ADR 0013: a person downloading in a browser is not a crawler working around
    a refusal, and a named AI block is taken as intent;
  - ADR 0019: manual documents are not refreshed;
  - ADR 0025: the new status.
- **Findings:** `docs/findings/ca-sbc.md`, with the per-carrier research, what
  was checked, and the counts.
- **Runbooks:** `docs/runbooks/california.md` gets a yearly SBC section;
  `docs/runbooks/sbc.md` gets import and awaiting-import notes.
- **README and CHANGELOG.**

## Data work (after the code)

1. Locate each carrier's federal SBCs, and record the evidence in the findings
   file:
   - by crawl: IEHP, Molina, Balance by CCHP, Sharp;
   - manual only: Kaiser, Blue Shield, WHA, Anthem, L.A. Care, Valley (decision 6).
2. Write `ca-2026.csv`, then run `apply-sbc-manifest`, `ingest-sbc STATES=CA
   YEAR=2026` and `check-sbc-manifest`.
3. **Your step:** download the manual carriers' SBCs in a browser, then run
   `make import-sbc DIR=… YEAR=2026`.
4. Run `sbc-report STATES=CA VERIFY=1`. Then a real question, e.g. Kaiser Silver
   70 HMO and urgent care, cited. Then `scripts/eval_sbc_ranking.py`, which must
   stay at or above 97%.

## Out of scope

- The Health Net links.
- Per-variant SBCs.
- Gating the 18-state crawl by the registry.
- SBC embeddings (SP3).
- Spanish documents.

## Tests (written after the features, as you direct)

`test_registry` (new status rules, `sbc_host_for`), `test_sbc_manifest`,
`test_sbc_import`, additions to `test_sbc_ingest`, `test_sbc_refresh`,
`test_sbc_report`, `test_ca_puf_load` (auto-apply), `test_tools`,
`test_generation` (note), and `test_sbc_hygiene` stays green. There is no real
document in any test.
