# Runbook — keeping the SBC collection current

What to run, and when, to keep plan documents current (ADR 0019). Everything
here runs on the machine that holds `data/sbc/`; nothing about these documents
runs in CI or in the cloud (ADR 0016).

Before any of it: `docker compose up -d db` and `make migrate`.

## Monthly

1. **Refresh the catalog.** Plans move to new links, and new plans appear.
   ```bash
   make ingest-plans STATES=<the loaded states> YEAR=2026
   ```
2. **Check for new issuer IDs of the top parents.** A parent can sell under a
   HIOS ID the enrollment data doesn't have (three appeared for 2026). Compare
   the catalog's issuer names with `src/ingestion/sbc/top_issuers.py`:
   ```sql
   SELECT DISTINCT hios_issuer_id, name FROM issuers WHERE plan_year = 2026 ORDER BY name;
   ```
   Add any match to its parent, with a `# 2026:` comment.
3. **Read what is new, then re-check what is stored.**
   ```bash
   make ingest-sbc STATES=<states> YEAR=2026     # new documents only
   make refresh-sbc STATES=<states> YEAR=2026    # asks about every stored one, retries failures
   ```
   Expect most documents to answer 304 or come back identical. A refresh is
   the only command that re-requests a document we already have.
4. **Measure.**
   ```bash
   make sbc-report YEAR=2026 VERIFY=1
   ```
   Look at: the share of plans with text, per state and issuer; new failure
   reasons, "no text layer" among them; documents no plan points at; plans the
   latest catalog run did not return; and any file whose hash no longer
   matches.
5. **Record anything that changed** in `docs/findings/sbc-documents.md`.

## When the next plan year opens (late October)

CMS publishes the next year's plans before open enrollment on 1 November.

1. **Smoke-test one county**, so a wrong year is cheap to discover:
   ```bash
   uv run python -m src.ingestion.plans --states NH --year 2027 --max-counties 1
   ```
2. **Load the catalog** for every state you cover, with `YEAR=2027`.
3. **Check issuer IDs again** (step 2 above), for 2027.
4. **Read the documents:** `make ingest-sbc STATES=<states> YEAR=2027`.
   Expect `wrong_year` while issuers still serve the current year's files at
   next year's links. Re-run `make refresh-sbc … YEAR=2027` weekly through
   November; a corrected file is picked up as a change.
5. **Keep the old year.** Its rows and PDFs stay: a saved plan card names the
   year it showed, and answers read a plan in that year.

## After a parser change

Bumping `PARSER_VERSION` makes every stored document outdated. They are
re-parsed from the kept PDFs, with no request to any issuer:

```bash
make ingest-sbc STATES=<states> YEAR=2026
uv run python -m scripts.eval_sbc_ranking --year 2026    # before and after
```

Check `make sbc-report` shows 0 documents on an older parser, and that the
file count and modification times are unchanged.

## Disk, and the one copy

- A kept PDF averages about 0.75 MB. `make sbc-report` prints the totals for
  `raw/`, `rejected/` and `archive/`.
- **`data/sbc/` is the only copy.** There is no backup, by choice; if this
  disk is lost, the documents have to be downloaded again, and any file an
  issuer has since changed or withdrawn is gone.
- Nothing deletes a downloaded PDF. A replaced one moves to `archive/`, and
  one refused as another year's moves to `rejected/`.

## If something looks wrong

- **A file's hash no longer matches** (`VERIFY=1`): something outside the
  pipeline changed it. Compare it with the archived copies before re-parsing.
- **A document's `checked_at` is months old:** the monthly refresh was missed,
  or that document keeps hitting a temporary failure; the run's summary names
  them as `unreachable`.
- **A host starts refusing:** the document's text is dropped and its plans'
  answers link the issuer's PDF. That is intended (ADR 0013); nothing works
  around a refusal.
