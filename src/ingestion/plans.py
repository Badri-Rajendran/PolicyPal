"""Plan catalog ingestion: `make ingest-plans STATES=TX,FL`.

Separate from `make ingest` on purpose — it needs a CMS key and, at full
scope, tens of thousands of requests, and building the corpus should need
neither. Not a `Source`: those produce chunks, this produces rows (ADR 0009).

Batch ingestion works because the catalog needs no household — only the
premium depends on age (docs/findings/cms-marketplace-api.md). Each county is
one transaction, so an interrupted run keeps every county it finished and a
re-run changes no row count.

    uv run python -m src.ingestion.plans --states TX --max-counties 2
"""
import argparse
import sys
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal

import requests
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from tqdm import tqdm

from src.core.db import get_session
from src.core.exceptions import MarketplaceApiKeyMissingError
from src.core.logging import get_logger
from src.core.marketplace_api import MARKETPLACE_STATES
from src.models.plan import Issuer, Plan, PlanCostShare, PlanCounty, ZipCounty

from .marketplace_api import County, counties_by_state, county_plans, county_zips

logger = get_logger(__name__)

# A plan missing any of these cannot be filtered or displayed, so it is
# skipped rather than written half-empty. Checked for None, not falsiness:
# `hsa_eligible: false` is a real answer.
_REQUIRED_PLAN_FIELDS = ("id", "name", "metal_level", "type", "state", "hsa_eligible", "has_national_network")
_REQUIRED_ISSUER_FIELDS = ("id", "name", "state")


def resolve_states(raw: str) -> list[str]:
    """`"tx, FL"` → `["TX", "FL"]`; `"ALL"` → every marketplace state."""
    requested = [code.strip().upper() for code in raw.split(",") if code.strip()]
    if not requested:
        raise ValueError("no states given")
    if "ALL" in requested:
        return list(MARKETPLACE_STATES)

    unknown = sorted(set(requested) - set(MARKETPLACE_STATES))
    if unknown:
        raise ValueError(
            f"not HealthCare.gov marketplace states: {', '.join(unknown)} "
            "(they run their own exchange, or are not state codes)"
        )
    return list(dict.fromkeys(requested))


def _money(value) -> Decimal | None:
    # Through str(), so 337.47 is stored as 337.47 and not its float neighbour.
    return None if value is None else Decimal(str(value))


def _is_complete(plan: dict) -> bool:
    issuer = plan.get("issuer") or {}
    return all(plan.get(f) not in (None, "") for f in _REQUIRED_PLAN_FIELDS) and all(
        issuer.get(f) not in (None, "") for f in _REQUIRED_ISSUER_FIELDS
    )


def _issuer_row(issuer: dict, year: int) -> dict:
    return {
        "hios_issuer_id": str(issuer["id"]),
        "plan_year": year,
        "name": issuer["name"],
        "state": issuer["state"],
        "individual_url": issuer.get("individual_url") or None,
        "toll_free": issuer.get("toll_free") or None,
        "tty": issuer.get("tty") or None,
    }


def _plan_row(plan: dict, year: int, issuer_id) -> dict:
    rating = plan.get("quality_rating") or {}
    return {
        "issuer_id": issuer_id,
        "hios_plan_id": plan["id"],
        "plan_year": year,
        "marketing_name": plan["name"],
        "metal_level": plan["metal_level"],
        "plan_type": plan["type"],
        "state": plan["state"],
        "premium_reference": _money(plan.get("premium")),
        "hsa_eligible": plan["hsa_eligible"],
        "has_national_network": plan["has_national_network"],
        "is_standardized_plan": plan.get("is_standardized_plan"),
        # CMS reports "not rated" as 0; star ratings run 1-5.
        "quality_rating_global": rating.get("global_rating") or None,
        "quality_rating_clinical": rating.get("clinical_quality_management_rating") or None,
        "quality_rating_enrollee": rating.get("enrollee_experience_rating") or None,
        "quality_rating_efficiency": rating.get("plan_efficiency_rating") or None,
        "quality_not_rated_reason": rating.get("global_not_rated_reason") or None,
        "benefits_url": plan.get("benefits_url") or None,
        "brochure_url": plan.get("brochure_url") or None,
        "formulary_url": plan.get("formulary_url") or None,
        "network_url": plan.get("network_url") or None,
    }


def _cost_share_rows(plan: dict, plan_id) -> list[dict]:
    """Deductibles and out-of-pocket maximums, one row per unique-key combination.

    Key fields default to "" rather than None: the unique constraint treats
    NULLs as distinct, which would let duplicates through.
    """
    rows = {}
    entries = 0
    for kind, field in (("deductible", "deductibles"), ("moop", "moops")):
        for entry in plan.get(field) or []:
            entries += 1
            row = {
                "plan_id": plan_id,
                "kind": kind,
                "cost_share_type": entry.get("type") or "",
                "csr_variant": entry.get("csr") or "",
                "network_tier": entry.get("network_tier") or "",
                "family_cost": entry.get("family_cost") or "",
                "amount": _money(entry.get("amount")),
            }
            key = (kind, row["cost_share_type"], row["csr_variant"], row["network_tier"], row["family_cost"])
            rows[key] = row

    # Dropping one means two entries shared a whole unique key — if this
    # fires, the key is missing a field and one value is being overwritten.
    if len(rows) < entries:
        logger.warning("plan %s: %d cost-share entries collapsed on the unique key", plan["id"], entries - len(rows))
    return list(rows.values())


def upsert(session, model, rows: list[dict], constraint: str, key: tuple[str, ...]) -> None:
    """Insert, or overwrite every non-key column: the latest sync wins.

    `updated_at` is set explicitly because ON CONFLICT DO UPDATE writes only
    what `set_` names — the column's `onupdate` never fires, and without this
    it would freeze at first insert.
    """
    stmt = insert(model).values(rows)
    mutable = {col: stmt.excluded[col] for col in rows[0] if col not in key}
    session.execute(stmt.on_conflict_do_update(constraint=constraint, set_=mutable | {"updated_at": func.now()}))


def _write_county(session, plans: list[dict], countyfips: str, year: int) -> tuple[int, int]:
    """Write one county's plans; returns `(plans, cost-share rows)` written."""
    # De-duplicated by id: one multi-row ON CONFLICT statement cannot touch the
    # same row twice, and adjacent pages can repeat a plan.
    by_id = {}
    for plan in plans:
        if _is_complete(plan):
            by_id[plan["id"]] = plan
        else:
            logger.warning("county %s: skipping incomplete plan %s", countyfips, plan.get("id"))
    if not by_id:
        return 0, 0
    plans = list(by_id.values())

    issuer_rows = {str(p["issuer"]["id"]): _issuer_row(p["issuer"], year) for p in plans}
    upsert(session, Issuer, list(issuer_rows.values()),
            "uq_issuers_hios_issuer_id_plan_year", ("hios_issuer_id", "plan_year"))
    issuer_ids = dict(session.execute(
        select(Issuer.hios_issuer_id, Issuer.id).where(
            Issuer.hios_issuer_id.in_(issuer_rows), Issuer.plan_year == year
        )
    ).all())

    plan_rows = [_plan_row(p, year, issuer_ids[str(p["issuer"]["id"])]) for p in plans]
    upsert(session, Plan, plan_rows, "uq_plans_hios_plan_id_plan_year", ("hios_plan_id", "plan_year"))
    plan_ids = dict(session.execute(
        select(Plan.hios_plan_id, Plan.id).where(Plan.hios_plan_id.in_(by_id), Plan.plan_year == year)
    ).all())

    session.execute(
        insert(PlanCounty)
        .values([{"plan_id": plan_id, "countyfips": countyfips} for plan_id in plan_ids.values()])
        .on_conflict_do_nothing(constraint="uq_plan_counties_plan_id_countyfips")
    )

    # Replaced rather than upserted: a variant a plan drops between syncs
    # would otherwise linger forever, with nothing to prune it by.
    session.execute(delete(PlanCostShare).where(PlanCostShare.plan_id.in_(plan_ids.values())))
    cost_rows = [row for p in plans for row in _cost_share_rows(p, plan_ids[p["id"]])]
    if cost_rows:
        session.execute(insert(PlanCostShare), cost_rows)

    return len(plan_rows), len(cost_rows)


def _write_zip_counties(session, counties: list[County], year: int) -> int:
    """Replace the year's ZIP-to-county crosswalk; returns the pairs written.

    Every state at once, whatever `--states` says: it is one bulk payload
    already in hand, and the chat path needs it to reject a ZIP outside the
    marketplace states as such, not as unknown.
    """
    rows = {
        (zipcode, county.fips): {
            "zipcode": zipcode,
            "plan_year": year,
            "countyfips": county.fips,
            "county_name": county.name,
            "state": county.state,
        }
        for county in counties
        for zipcode in county.zips
    }
    session.execute(delete(ZipCounty).where(ZipCounty.plan_year == year))
    if rows:
        session.execute(insert(ZipCounty), list(rows.values()))
    return len(rows)


def _describe(exc: Exception) -> str:
    # SQLAlchemy errors carry the statement and every bound parameter — one
    # county's worth of rows. The first line says what went wrong.
    return str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__


def execute(states: list[str], year: int, max_counties: int | None = None) -> None:
    crosswalk = county_zips(year)
    with get_session() as session:
        pairs = _write_zip_counties(session, crosswalk, year)
    print(f"{pairs} ZIP-to-county pairs recorded for {year}")

    counties = counties_by_state(crosswalk)
    totals = Counter()

    for state in states:
        print(f"\n=== Ingesting plans: {state} ({year}) ===")
        state_counties = counties.get(state, [])[:max_counties]
        if not state_counties:
            print(f"  {state}: no counties in /data/county-zips, skipping")
            logger.warning("no counties for %s in plan year %d", state, year)
            totals["states_skipped"] += 1
            continue

        for countyfips, zipcode in tqdm(state_counties, desc=state):
            try:
                plans = county_plans(state, countyfips, zipcode, year)
                with get_session() as session:
                    written, shares = _write_county(session, plans, countyfips, year)
            except (requests.RequestException, ValueError, SQLAlchemyError) as exc:
                # One county failing must not end a multi-state run.
                totals["counties_failed"] += 1
                print(f"  {countyfips}: ERROR — {_describe(exc)}")
                logger.warning("plan ingest failed for county %s: %s", countyfips, _describe(exc))
                continue
            totals["counties"] += 1
            totals["plans"] += written
            totals["cost_shares"] += shares

    # Counts are writes, not table rows: a plan sold in several counties is
    # upserted once per county, into the same row.
    print(
        f"\n{totals['counties']} counties ingested, {totals['counties_failed']} failed; "
        f"{totals['plans']} plan and {totals['cost_shares']} cost-share writes"
    )
    logger.info("plan ingest finished: %s", dict(totals))


def parse_args(args):
    parser = argparse.ArgumentParser(description="Ingest the CMS Marketplace plan catalog.")
    parser.add_argument("--states", required=True,
                        help="Comma-separated state codes, or ALL, e.g. TX,FL")
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year,
                        help="Plan year (default: this year). During open enrollment, pass next year explicitly.")
    parser.add_argument("--max-counties", type=int, default=None,
                        help="Cap counties per state, for a quick smoke run")
    parsed = parser.parse_args(args)

    try:
        parsed.states = resolve_states(parsed.states)
    except ValueError as exc:
        parser.error(str(exc))
    if parsed.max_counties is not None and parsed.max_counties < 1:
        parser.error("--max-counties must be at least 1")
    return parsed


def main(args=sys.argv[1:]):
    parsed = parse_args(args)
    try:
        execute(parsed.states, parsed.year, parsed.max_counties)
    except MarketplaceApiKeyMissingError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    main()
