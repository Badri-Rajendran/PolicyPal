# 0025 — Every source is recorded in a committed registry, and only approved ones run

## Status

Accepted. Records in data what ADR 0003 (corpus sources) and ADR 0013 (SBC
copyright) decided in prose.

## Context

PolicyPal is a pilot that may become commercial. Its sources differ in licence:
- Wikipedia is CC BY-SA;
- HealthCare.gov and CMS data are US government works (17 U.S.C. § 105);
- issuer SBCs are copyrighted mandated disclosures;
- Covered California reserves all rights and forbids automated access.

Those decisions lived in ADR prose and code comments. A commercial launch has to
be able to list every source, its licence and permission status, and how to
take it out. Nothing stopped a new source from running without that being
written down.

## Decision

`src/ingestion/sources/registry.toml` holds one `[[source]]` per source,
enabled or refused, read with the standard library's `tomllib`, so there is no
new dependency:

| Field | Values |
| --- | --- |
| `kind` | `corpus`, `catalog`, `sbc_host`, `directory` |
| `jurisdiction` | `US` or a state code |
| `permission_status` | `public_domain`, `open_license`, `written_permission`, `pending_review`, `denied` |
| `commercial_use` | `yes`, `no`, `review` |
| `robots` | `allowed`, `disallowed`, `unavailable`, `not_applicable`; `robots_checked_on` is required unless `not_applicable` |
| `access` | `api`, `download`, `crawl`, `manual`, `link` |

Every entry also has `id`, `name`, `publisher`, `scope_urls`, `license`,
`license_url`, `verified_on`, `enabled`, `removal` and `notes`.

`src/ingestion/sources/registry.py` enforces the rules when the registry loads:
- required fields are present, and no unknown field;
- values are from the lists above;
- ids are unique;
- `enabled = true` needs `public_domain`, `open_license` or `written_permission`.

An invalid registry fails the import, so a bad edit cannot quietly enable
anything.

- `SOURCES`, the corpus sources the pipeline runs, is filtered at import to
  those the registry enables.
- `ALL_SOURCES` lists them all; a test requires each to have an entry.
- The California plan loader calls `require_enabled("cms_ca_sbe_puf")` before
  fetching.
- A refused source is recorded too, disabled, with the reason. Covered
  California is `denied` with `access = "link"`, so the decision is not
  re-litigated.

## Consequences

- A new source cannot run without an entry, and its removal steps are written
  down when it is added.
- The registry is a record, not a permission. A commercial launch still needs
  legal review of every enabled entry. `commercial_use = "yes"` records what
  the licence says, not a legal opinion.
- Entries go stale: `verified_on` and `robots_checked_on` say when each was last
  checked, and the California runbook re-checks its entries yearly.
