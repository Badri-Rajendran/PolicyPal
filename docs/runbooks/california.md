# Runbook — California plans (Covered California)

California's plans come from CMS's state-based exchange PUF, not the
Marketplace API (ADR 0024). The file for a plan year appears **May to August
of that year**, so this is a yearly routine, not a monthly one.

## Prerequisites

- `docker compose up -d db` and `make migrate`.
- A ZIP-to-county crosswalk for the plan year. `make ingest-ca-plans` fetches
  CMS's if it is missing, which needs `CMS_MARKETPLACE_API_KEY`. Any
  `make ingest-plans` run for that year also writes it.

## Every year, May to August

1. **Look for the file.**

   ```sh
   make ingest-ca-plans YEAR=2027
   ```

   Exit status 3 with "CMS has not published the 2027 California PUF yet" means
   try again in a few weeks. Nothing was written.
2. **Re-check the rating areas** against
   <https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra>.
   Update `src/ingestion/ca_puf/rating_areas.py`, with the date, if anything
   moved.
3. **Re-check the issuers.**
   - Covered California's rates announcement names the year's carriers. The
     2026 one came out on 2025-08-14.
   - A new HIOS issuer ID fails the load with `issuer … is not in CA_ISSUERS`.
     Add it to `src/ingestion/ca_puf/issuers.py` with where the name came from.
     Never guess.
4. **Read the load's summary**, and compare it with the previous year's in
   [docs/findings/ca-sbe-puf.md](../findings/ca-sbe-puf.md):

   ```
   <plans> plans from <issuers> issuers, file <label>: <n> plan-county rows (<m> dropped: no rate there), <r> rates
   Los Angeles ZIPs with no CMS rating area, shown unpriced: ...
   ```

   Record the new numbers there.
5. **Check it in the app:** a Los Angeles ZIP (90012) and one outside it. Plans
   are for the new year, and no longer marked prior-year.
6. **Seed Azure.** Take a dump of the local database and restore it, following
   the deploy runbook. Then check the restored database:

   ```sql
   select plan_year, count(*) from plans where catalog_source = 'ca_sbe_puf' group by 1;  -- 2026 | 190
   select file_label, loaded_at from catalog_loads order by loaded_at desc limit 1;
   ```

Keep the previous year loaded. Its SBC answers and saved plan cards still refer
to it.

## SBC documents, every year after the load

The PUF has no SBC links, so California's come from a committed, hand-built
manifest: `src/ingestion/sbc/manifests/ca-<year>.csv` (ADR 0026). Each row's
host must have an `sbc_host` entry in `src/ingestion/sources/registry.toml`.

1. **Re-check each carrier's entry.** Before any automated request, re-read
   its `robots.txt` **and** its website Terms. If the Terms now ban robots or
   scrapers, set `access = "manual"`, whatever `robots.txt` says. Update
   `robots_checked_on` and `verified_on`.
2. **Write the new year's manifest.** Start from last year's file.
   - For a `crawl` carrier, find each plan's SBC on its listing page.
   - For a `manual` carrier, open its page in a browser. Never use a script.
   - Set `verified_on` on each row. A new plan ID with no row is shown with no
     link. [docs/findings/ca-sbc.md](../findings/ca-sbc.md) records where each
     carrier publishes.
3. **Apply it, then read what can be crawled:**

   ```sh
   make apply-sbc-manifest YEAR=2027
   make ingest-sbc STATES=CA YEAR=2027
   ```

   `make ingest-ca-plans` applies the manifest itself when the file exists. The
   ingest counts the links "awaiting a manual import" and never requests them.
4. **Download the manual carriers' SBCs in a browser,** into one folder. Keep
   each file's name exactly as the link's last path segment. Then:

   ```sh
   make import-sbc YEAR=2027 DIR=~/Downloads/ca-sbc-2027
   make import-sbc YEAR=2027 FILE=path/to/file.pdf URL=<the manifest's link>   # when names differ
   ```

   `DIR=` imports only a file whose name matches exactly one manual-only link,
   and reports the rest.
5. **Check it:**

   ```sh
   make check-sbc-manifest YEAR=2027
   make sbc-report STATES=CA YEAR=2027 VERIFY=1
   ```

   Open each name mismatch in the check: carriers print plan names their own
   way, so a mismatch is not always wrong. Fix any row that points at another
   plan's document, apply it again, and re-import. Record the counts in the
   findings file.

**Removing a carrier:** set its entry's `enabled = false`, then
`make apply-sbc-manifest YEAR=…`. Its plans lose their link. Its documents and
PDFs are kept (ADR 0016), and no plan points at them any more.

## If a load fails

It changes nothing: validation runs before the first write, and the previous
load keeps serving. The message names the rule broken:

| Message | What to do |
| --- | --- |
| `issuer … is not in CA_ISSUERS` | Add the issuer (step 3). |
| `county … is not in the California rating-area map` | CMS changed the counties; check step 2. |
| `plan … is rated in area N, where it is not sold` | The map is wrong for some county, or CMS changed a plan's areas. Compare the map with the CMS page before changing anything. |
| `plan … has no rates` or `is sold in no county` | The file is incomplete. Wait for CMS's next update rather than load it. |
| `… has no column '…'` | CMS changed the file's format. Update `read.py` and its tests. |

## Removing California

Delete plans where `catalog_source = 'ca_sbe_puf'`; their counties, cost
shares and rates go with them. Then delete the `state = 'CA'` rows of
`rating_areas`. The registry entry `cms_ca_sbe_puf` says the same.
