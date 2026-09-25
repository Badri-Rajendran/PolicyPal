"""Write a read California PUF into the catalog: one transaction, validated first.

Every rule is checked before the first write, so a bad file changes nothing and
the previous load keeps serving. The caller owns the transaction (get_session).
"""
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, insert, select

from src.models.plan import (
    CatalogLoad,
    Issuer,
    Plan,
    PlanCostShare,
    PlanCounty,
    PlanRate,
    RatingArea,
    ZipCounty,
)

from ..plans import upsert
from .issuers import UnknownIssuerError, issuer_name
from .rating_areas import (
    LOS_ANGELES,
    UnmappedCountyError,
    area_for,
    county_area,
    table_rows,
)
from .read import IN_NETWORK, INDIVIDUAL, Puf

STATE = "CA"
CATALOG_SOURCE = "ca_sbe_puf"
_NOT_SOLD = object()


class LoadError(ValueError):
    """The file breaks a rule; nothing was written. The message says which."""


@dataclass(frozen=True)
class LoadReport:
    plans: int
    issuers: int
    plan_counties: int
    dropped_unrated: int
    rates: int
    unrated_zips: tuple[str, ...]


def _counties(session, year: int) -> dict[str, tuple[str, ...]]:
    """California's counties and their ZIPs, from the year's CMS crosswalk."""
    rows = session.execute(
        select(ZipCounty.countyfips, ZipCounty.zipcode).where(ZipCounty.state == STATE, ZipCounty.plan_year == year)
    ).all()
    counties: dict[str, list[str]] = defaultdict(list)
    for fips, zipcode in rows:
        counties[fips].append(zipcode)
    return {fips: tuple(sorted(zips)) for fips, zips in counties.items()}


def _zips_sold(fips: str, partial: tuple[str, ...] | None, all_zips: tuple[str, ...], rated: set[int]):
    """The ZIPs of a county a plan is sold in: None for all of them, _NOT_SOLD for none."""
    if fips != LOS_ANGELES:
        return partial if county_area(fips) in rated else _NOT_SOLD
    candidates = partial or all_zips
    if not any(area_for(fips, z) in rated for z in candidates):
        return _NOT_SOLD
    # A ZIP with no rating area stays: the plan is sold there, just not priceable.
    kept = tuple(z for z in candidates if area_for(fips, z) is None or area_for(fips, z) in rated)
    return None if partial is None and set(kept) == set(all_zips) else kept


def _merge(current, zips):
    """Two service-area rows for one county: the whole county wins, else the union."""
    if current is None or zips is None:
        return None
    return tuple(sorted(set(current) | set(zips)))


def sold_counties(puf: Puf, counties: dict[str, tuple[str, ...]]):
    """Each plan's counties, with their ZIPs where it is sold in only some, and the pairs dropped.

    A plan is sold in a service-area county only where it has a rate for that
    county's rating area: Western Health Advantage files one service area over
    areas 2 and 3, with a separate plan for each.
    """
    rated: dict[str, set[int]] = defaultdict(set)
    for plan_id, area, _age in puf.rates:
        rated[plan_id].add(area)
    by_area = defaultdict(list)
    for service_area in puf.service_areas:
        by_area[(service_area.issuer_id, service_area.service_area_id)].append(service_area)

    sold: dict[str, dict[str, tuple[str, ...] | None]] = {}
    dropped = 0
    for plan in puf.plans:
        areas = rated.get(plan.hios_plan_id)
        if not areas:
            raise LoadError(f"plan {plan.hios_plan_id} has no rates")
        mine: dict[str, tuple[str, ...] | None] = {}
        for service_area in by_area[(plan.issuer_id, plan.service_area_id)]:
            for fips in ([service_area.countyfips] if service_area.countyfips else sorted(counties)):
                if fips not in counties:
                    raise LoadError(f"plan {plan.hios_plan_id}: county {fips} is not in the ZIP-to-county crosswalk")
                zips = _zips_sold(fips, service_area.zipcodes, counties[fips], areas)
                if zips is _NOT_SOLD:
                    dropped += 1
                    continue
                mine[fips] = _merge(mine[fips], zips) if fips in mine else zips
        if not mine:
            raise LoadError(f"plan {plan.hios_plan_id} is sold in no county")
        where = set()
        for fips, zips in mine.items():
            where |= {area_for(fips, z) for z in (zips or counties[fips])} - {None}
        if stray := sorted(areas - where):
            # A rate in an area the plan is not sold in: the map is wrong for some county.
            raise LoadError(f"plan {plan.hios_plan_id} is rated in area {stray[0]}, where it is not sold")
        sold[plan.hios_plan_id] = mine
    return sold, dropped


def load(session, puf: Puf, *, year: int, file_url: str, sha256: str) -> LoadReport:
    if not puf.plans:
        # Never reach the delete below with an empty list: NOT IN () would match every CA plan.
        raise LoadError("the file has no plans; nothing was changed")
    counties = _counties(session, year)
    if not counties:
        raise LoadError(f"no California ZIP-to-county crosswalk for {year}: run `make ingest-plans` for that year first")
    try:
        rating_rows = table_rows(counties)
        names = {plan.issuer_id: issuer_name(plan.issuer_id) for plan in puf.plans}
    except (UnmappedCountyError, UnknownIssuerError) as exc:
        raise LoadError(str(exc)) from None
    sold, dropped = sold_counties(puf, counties)
    unrated_zips = tuple(z for z in counties.get(LOS_ANGELES, ()) if area_for(LOS_ANGELES, z) is None)

    # Validated: from here on, only writes.
    upsert(session, Issuer, [{"hios_issuer_id": issuer, "plan_year": year, "name": name, "state": STATE}
                             for issuer, name in sorted(names.items())],
           "uq_issuers_hios_issuer_id_plan_year", ("hios_issuer_id", "plan_year"))
    issuer_ids = dict(session.execute(
        select(Issuer.hios_issuer_id, Issuer.id).where(Issuer.plan_year == year, Issuer.hios_issuer_id.in_(names))
    ).all())
    upsert(session, Plan, [{
        "issuer_id": issuer_ids[plan.issuer_id], "hios_plan_id": plan.hios_plan_id, "plan_year": year,
        "marketing_name": plan.marketing_name, "metal_level": plan.metal_level, "plan_type": plan.plan_type,
        "state": STATE, "premium_reference": None, "hsa_eligible": plan.hsa_eligible,
        "has_national_network": plan.has_national_network, "catalog_source": CATALOG_SOURCE,
    } for plan in puf.plans], "uq_plans_hios_plan_id_plan_year", ("hios_plan_id", "plan_year"))

    ids = [plan.hios_plan_id for plan in puf.plans]
    # The file is authoritative: a plan it no longer lists goes, with its rows.
    session.execute(delete(Plan).where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE,
                                       Plan.hios_plan_id.not_in(ids)))
    plan_ids = dict(session.execute(
        select(Plan.hios_plan_id, Plan.id).where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE)
    ).all())
    for model in (PlanCounty, PlanCostShare, PlanRate):
        session.execute(delete(model).where(model.plan_id.in_(list(plan_ids.values()))))

    county_rows = [{"plan_id": plan_ids[plan_id], "countyfips": fips, "zipcodes": list(zips) if zips else None}
                   for plan_id, where in sold.items() for fips, zips in where.items()]
    share_rows = [{"plan_id": plan_ids[s.hios_plan_id], "kind": s.kind, "cost_share_type": s.cost_share_type,
                   "csr_variant": s.csr_variant, "network_tier": IN_NETWORK, "family_cost": INDIVIDUAL,
                   "amount": s.amount} for s in puf.cost_shares]
    rate_rows = [{"plan_id": plan_ids[plan_id], "rating_area": area, "age": age, "individual_rate": rate}
                 for (plan_id, area, age), rate in puf.rates.items()]
    for model, rows in ((PlanCounty, county_rows), (PlanCostShare, share_rows), (PlanRate, rate_rows)):
        if rows:
            session.execute(insert(model), rows)

    session.execute(delete(RatingArea).where(RatingArea.plan_year == year, RatingArea.state == STATE))
    session.execute(insert(RatingArea), [{"state": STATE, "plan_year": year, "countyfips": fips, "zip3": zip3,
                                          "rating_area": area} for fips, zip3, area in rating_rows])
    session.add(CatalogLoad(source=CATALOG_SOURCE, state=STATE, plan_year=year, file_url=file_url,
                            file_label=puf.label, sha256=sha256, plans=len(ids)))
    session.flush()
    return LoadReport(plans=len(ids), issuers=len(names), plan_counties=len(county_rows), dropped_unrated=dropped,
                      rates=len(rate_rows), unrated_zips=unrated_zips)
