# 0026 — California's SBCs: a hand-built manifest, website Terms, and manual import

## Status

Accepted. Sub-project 2 of the California expansion. It amends three earlier
ADRs:

- **ADR 0013.** For California, a carrier's website Terms can refuse us, as well
  as its `robots.txt` and HTTP replies. A person downloading a document in a
  browser is not the crawler working around a refusal.
- **ADR 0019.** A document imported by hand is never re-requested, not even by
  `refresh-sbc`.
- **ADR 0025.** Adds the permission status `mandated_disclosure`, and enabling
  an entry now accepts it.

## Context

California's plans come from CMS's state-based exchange PUF (ADR 0024). Its SBC
URL column is empty on every row, so every California coverage question ended
with "no Summary of Benefits and Coverage link is listed for this plan". The
SBC pipeline could not help as it stood:

- it accepted only the 30 HealthCare.gov states;
- it read only `plans.benefits_url`, which CMS fills for those states;
- it had no way to take a PDF a person had downloaded.

The 11 carriers were researched one by one on 2026-09-25 and 2026-09-26. The
evidence is in [docs/findings/ca-sbc.md](../findings/ca-sbc.md). In short:

- **They publish SBCs in very different ways:**
  - named by HIOS ID (Kaiser);
  - named by metal level (IEHP);
  - by internal codes;
  - only behind a search form (Health Net).

  Their pages print no HIOS IDs, so there is no reliable way to match a
  document to a plan automatically.
- **Most carriers' website Terms restrict what we do, even where `robots.txt`
  allows us.**
  - Kaiser, Blue Shield, Western Health Advantage and Anthem expressly ban
    robots, spiders or scrapers; L.A. Care appears to as well.
  - Nearly all of them limit use to personal, non-commercial purposes, or bar
    reproduction without written consent.

  The registry already records Covered California as `denied` with the note
  "robots.txt allows everything; the Terms govern".
- **One carrier's `robots.txt` also names AI crawlers** (L.A. Care), and one
  host blocks automated clients outright (Valley Health Plan).

## Decision

### A hand-built, committed manifest

`src/ingestion/sbc/manifests/ca-<year>.csv` lists
`hios_plan_id,plan_year,sbc_url,verified_on,note`. A person finds and checks
each row. It holds public URLs and plan IDs only, never a document or an
excerpt. An automatic "proposal helper", which would have scraped listing pages
and matched names, was dropped: most carriers' pages don't suit it, and several
carriers' Terms forbid it.

`src/ingestion/sbc/manifest.py`:

- **`load_manifest`** checks the file without a database:
  - the header;
  - the California plan ID format;
  - the year;
  - that the URL is HTTPS on a public host (`fetch.unsafe_reason`);
  - that a California `sbc_host` registry entry covers the URL;
  - the date;
  - no plan listed twice.

  Any failure names the line, and nothing is applied.
- **`apply_manifest` is authoritative for California.**
  - Every `ca_sbe_puf` plan of the year gets its row's URL, or NULL when it has
    no row or its host's entry is disabled.
  - A plan in the manifest that isn't loaded is an error.
  - Disabling a carrier's entry and applying again is how a carrier is removed.
- **Where it runs.** `make apply-sbc-manifest YEAR=` runs it, and so does
  `make ingest-ca-plans` after a load, when the year's manifest exists. A bad
  manifest leaves the plans loaded and exits non-zero, saying the links were
  not applied.
- **`make check-sbc-manifest YEAR=` is the human check after an ingest.** It
  lists:
  - documents whose printed title lacks a word of the plan's name;
  - failures;
  - plans awaiting a manual import;
  - links not read yet;
  - plans with no link.

### Each carrier is a registry entry, with a new status

Each California carrier whose SBCs are used has one `sbc_<carrier>` entry of
`kind = "sbc_host"`. Its `scope_urls` are exact URL prefixes, and the longest
matching prefix wins (`registry.sbc_host_for`). The registry now requires every
prefix, of any kind, to be `https://host/…`, so a prefix can't also match a
look-alike host.

Its `permission_status` is the new **`mandated_disclosure`**. It means "federal
law requires the issuer to give this document to anyone shopping", which is
ADR 0013's basis for using SBCs at all. It is **not** a licence, and validation
enforces both of these:

- only an `sbc_host` may use it;
- its `commercial_use` must be `review`.

A commercial launch needs a legal review of every one of these entries.

### Website Terms govern, as for Covered California

A carrier is crawled only when **neither** its `robots.txt` **nor** its website
Terms refuse automated access.

- **Where the Terms ban robots or scrapers, the entry is `access = "manual"`.**
  This applies to Kaiser, Blue Shield, Western Health Advantage, Anthem and
  L.A. Care. It also applies to Valley Health Plan, whose host blocks automated
  clients. No automated request is made to these hosts at all, including probes
  and listing pages.
- **Where neither refuses, the entry is `access = "crawl"`,** read by the normal
  fetcher with all of ADR 0013's checks. This applies to IEHP, Molina, Balance
  by CCHP and Sharp. Sharp's SBC folder isn't under the path its `robots.txt`
  disallows.
- **Health Net is recorded but disabled.** Its SBCs are only reachable through
  a search form, and its plans keep "no link" and point to Covered California.

### California links are gated at the start of the crawl

`make ingest-sbc STATES=CA` now works: `resolve_states` takes the allowed
list, and the SBC ingest and report pass `CATALOG_STATES`. `ALL` still means
the 30 API states.

For a plan in a filed-rate state, `ingest.execute` sorts each link by its
host's entry:

| Entry | What happens |
| --- | --- |
| enabled, `crawl` | fetched |
| enabled, `manual` | never requested; counted as awaiting `make import-sbc` |
| disabled or missing | skipped and counted |

The HealthCare.gov states' links come from CMS and are read as before.
Extending the registry gate, and this Terms rule, to them is a follow-up, not
part of this decision.

### Manual import: a person downloads, the pipeline only reads

`make import-sbc YEAR= FILE= URL=`, or `DIR=`. `DIR=` matches each file to the
one manual-only link whose file name it has.

1. **Checks, before anything is written:**
   - the URL is some plan's link that year;
   - its host's entry is enabled;
   - the file is a PDF (`fetch.looks_like_pdf`) of at most `MAX_BYTES`.
2. **Copy.** Any cached file with other bytes is archived (ADR 0016). The file
   is copied to the link's cache path; the person's own file is left where it is.
3. **Parse.** `ingest_document(..., acquisition="manual")` parses it exactly as
   a crawled one: the cached copy is served and no request is made.

A person opening a carrier's page and saving its SBC is what any shopper does,
and what the document exists for. So it is not the crawler working around a
refusal, which ADR 0013 still forbids. Where the Terms limit use to personal
or non-commercial purposes, that limit is recorded as `commercial_use =
"review"` and stands until a legal review.

### Provenance

`sbc_documents.acquisition` is `crawl` or `manual`, NOT NULL, default `crawl`.

- `_store` writes it only when given, so a re-parse keeps `manual`.
- A manual document is never re-requested.
  - `ingest-sbc` re-parses it from disk after a parser change.
  - If its file is missing, `ingest-sbc` asks for a re-import instead of a
    fetch.
  - `refresh-sbc` never asks the carrier about it.
- `sbc-report` counts documents read by each route.

### Answers say the SBC is the standard plan's

A California plan's SBC is its standard (`-01`) version. People who qualify
for cost-sharing reductions, or American Indian and Alaska Native cost
sharing, pay less than it shows.

- When `plan_coverage` quotes a passage from a filed-rate state's plan, the
  answer opens with a notice saying so. The server writes it, with the same
  mechanism as the prior-year notice (`ToolOutcome.notice`), so it appears
  exactly where it is true.
- A first version put a `note` in the tool result and told the model to
  include it. In a live question the model left it out, so that approach was
  dropped.

Per-variant SBCs are a follow-up.

## Consequences

- **Answers depend on a person, yearly.** Most California carriers' SBCs come
  from someone downloading them in a browser. The California runbook adds this
  to the yearly routine, and `check-sbc-manifest` shows what is outstanding.
- **Commercial use is not settled.** Nearly every carrier limits use to
  personal or non-commercial purposes. A pilot can proceed on a mandated
  disclosure, but a launch needs each `mandated_disclosure` entry reviewed,
  and possibly written permission.
- **The 30-state crawl is now inconsistent with this rule.** It reads, for
  example, Anthem's SBCs for other states, and Anthem's Terms ban robots. This
  is recorded here and left for a follow-up decision, not changed silently.
- **A wrong manifest row shows up as a name mismatch,** not as an error. The
  check lists it and a person decides; carriers print plan names their own way.
- **Removing a carrier is two steps:** disable its entry, then run
  `apply-sbc-manifest`. Its documents and PDFs stay (ADR 0016), and no plan
  links to them any more.
