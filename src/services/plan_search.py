"""Marketplace plan search: the catalog filters, CMS prices (ADR 0010).

Which plans are sold in a county, and their deductibles, come from the
ingested tables. The premium comes live from CMS for the user's age: age
factors differ between issuers, so an age-27 order does not hold at other
ages (docs/findings/cms-marketplace-api.md, third pass).

ZIP and age are personal data. Nothing here logs either.
"""
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Literal

import requests
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import SQLAlchemyError

from src.core.db import get_session
from src.core.exceptions import MarketplaceApiKeyMissingError
from src.core.logging import get_logger
from src.core.marketplace_api import (
    MARKETPLACE_STATES,
    MAX_PREMIUM_BATCH,
    age_rated_premiums,
)
from src.models.plan import Issuer, Plan, PlanCostShare, PlanCounty, ZipCounty

logger = get_logger(__name__)

# The one cost-share variant a person without cost-sharing reductions pays,
# in network. CSR variants have lower deductibles and would understate them.
_NO_CSR = "Exchange variant (no CSR)"
_IN_NETWORK = "In-Network"
_INDIVIDUAL = "Individual"
_COMBINED_DEDUCTIBLE = "Combined Medical and Drug EHB Deductible"
_MEDICAL_DEDUCTIBLE = "Medical EHB Deductible"
_DRUG_DEDUCTIBLE = "Drug EHB Deductible"
_TOTAL_MOOP = "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"

SHOWN_PLANS = 10

# Catastrophic plans are sold only to people under 30 or with a hardship
# exemption, but CMS still prices them for any age. HealthCare.gov hides them
# from anyone older unless asked; so does this.
_CATASTROPHIC = "Catastrophic"
_CATASTROPHIC_MAX_AGE = 29

SortBy = Literal["premium", "deductible"]


@dataclass(frozen=True)
class PlanFilters:
    metal_level: str | None = None
    plan_type: str | None = None
    max_deductible: int | None = None
    sort_by: SortBy = "premium"
    include_catastrophic: bool = True


@dataclass(frozen=True)
class PlanResult:
    hios_plan_id: str
    plan_year: int
    name: str
    issuer: str
    metal_level: str
    plan_type: str
    # None when CMS gave no live price; premium_reference is then the only figure.
    monthly_premium: Decimal | None
    premium_reference: Decimal | None
    # The combined deductible, else the medical one; a separate drug
    # deductible is reported beside it rather than dropped.
    deductible: Decimal | None
    drug_deductible: Decimal | None
    out_of_pocket_max: Decimal | None
    hsa_eligible: bool
    quality_rating: int | None

    @property
    def premium_is_live(self) -> bool:
        return self.monthly_premium is not None


@dataclass(frozen=True)
class CountyOption:
    fips: str
    name: str
    state: str


@dataclass(frozen=True)
class PlanSearchResult:
    status: Literal[
        "ok", "zip_not_found", "not_marketplace_state", "ambiguous_county", "county_not_loaded", "no_match"
    ]
    plans: tuple[PlanResult, ...] = ()
    total_matching: int = 0
    plan_year: int | None = None
    county: CountyOption | None = None
    counties: tuple[CountyOption, ...] = ()
    state: str | None = None
    catastrophic_excluded: bool = False


def plan_catalog_available() -> bool:
    """Whether any plan is ingested — the gate on offering the tool at all.

    Not cached: a False cached at startup would hide a catalog ingested since.
    A database failure reads as "no catalog", which leaves chat as it was.
    """
    try:
        with get_session() as session:
            return bool(session.scalar(select(exists().select_from(Plan))))
    except SQLAlchemyError:
        logger.warning("could not check the plan catalog; plan search disabled for this request")
        return False


def _counties_for_zip(session, zip_code: str) -> tuple[int | None, list[CountyOption]]:
    """The ZIP's counties in the latest plan year its own county has plans for.

    Not the latest year with any plans: `zip_counties` is written for every
    state on each run, so mid-rollover, with next year ingested for only some
    states, that would pick a year this ZIP's county has nothing loaded for.
    Failing that (the county is loaded in no year), the latest year with any
    plans, so the ZIP is still placed in its state.
    """
    loaded = exists().where(
        PlanCounty.countyfips == ZipCounty.countyfips,
        PlanCounty.plan_id == Plan.id,
        Plan.plan_year == ZipCounty.plan_year,
    )
    year = session.scalar(
        select(func.max(ZipCounty.plan_year)).where(ZipCounty.zipcode == zip_code, loaded)
    ) or session.scalar(
        select(func.max(ZipCounty.plan_year)).where(
            ZipCounty.zipcode == zip_code, ZipCounty.plan_year.in_(select(Plan.plan_year).distinct())
        )
    )
    if year is None:
        return None, []
    rows = session.execute(
        select(ZipCounty.countyfips, ZipCounty.county_name, ZipCounty.state)
        .where(ZipCounty.zipcode == zip_code, ZipCounty.plan_year == year)
        .order_by(ZipCounty.countyfips)
    ).all()
    return year, [CountyOption(*row) for row in rows]


def _cost_shares():
    """One row per plan: its no-CSR, in-network, individual deductibles and moop."""
    amount = PlanCostShare.amount

    def of(kind: str, cost_share_type: str):
        return func.max(amount).filter(
            and_(PlanCostShare.kind == kind, PlanCostShare.cost_share_type == cost_share_type)
        )

    return (
        select(
            PlanCostShare.plan_id,
            of("deductible", _COMBINED_DEDUCTIBLE).label("combined"),
            of("deductible", _MEDICAL_DEDUCTIBLE).label("medical"),
            of("deductible", _DRUG_DEDUCTIBLE).label("drug"),
            of("moop", _TOTAL_MOOP).label("moop"),
        )
        .where(
            PlanCostShare.csr_variant == _NO_CSR,
            PlanCostShare.network_tier == _IN_NETWORK,
            PlanCostShare.family_cost == _INDIVIDUAL,
        )
        .group_by(PlanCostShare.plan_id)
        .subquery()
    )


def find_plans(session, *, countyfips: str, year: int, filters: PlanFilters, limit: int) -> tuple[list[PlanResult], int]:
    """Plans sold in the county that pass the filters, and how many there are in all.

    Ordered by the stored age-27 premium or by deductible. The caller re-sorts
    on live premiums; this order only decides which plans are candidates.
    """
    shares = _cost_shares()
    deductible = func.coalesce(shares.c.combined, shares.c.medical)

    conditions = [
        Plan.plan_year == year,
        Plan.id.in_(select(PlanCounty.plan_id).where(PlanCounty.countyfips == countyfips)),
    ]
    if filters.metal_level:
        conditions.append(Plan.metal_level == filters.metal_level)
    if filters.plan_type:
        conditions.append(Plan.plan_type == filters.plan_type)
    if not filters.include_catastrophic:
        conditions.append(Plan.metal_level != _CATASTROPHIC)
    if filters.max_deductible is not None:
        conditions.append(deductible <= filters.max_deductible)

    base = (
        select(Plan, Issuer.name.label("issuer_name"), deductible.label("deductible"),
               shares.c.drug, shares.c.moop)
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .outerjoin(shares, shares.c.plan_id == Plan.id)
        .where(*conditions)
    )
    total = session.scalar(select(func.count()).select_from(base.subquery()))

    if filters.sort_by == "deductible":
        order = (deductible.asc().nulls_last(), Plan.premium_reference.asc().nulls_last())
    else:
        order = (Plan.premium_reference.asc().nulls_last(),)
    rows = session.execute(base.order_by(*order, Plan.hios_plan_id).limit(limit)).all()

    return [
        PlanResult(
            hios_plan_id=plan.hios_plan_id,
            plan_year=plan.plan_year,
            name=plan.marketing_name,
            issuer=issuer_name,
            metal_level=plan.metal_level,
            plan_type=plan.plan_type,
            monthly_premium=None,
            premium_reference=plan.premium_reference,
            deductible=ded,
            drug_deductible=drug,
            out_of_pocket_max=moop,
            hsa_eligible=plan.hsa_eligible,
            quality_rating=plan.quality_rating_global,
        )
        for plan, issuer_name, ded, drug, moop in rows
    ], total


def _price(plans: list[PlanResult], *, age: int, county: CountyOption, zip_code: str, year: int) -> list[PlanResult]:
    """Attach live premiums. A CMS failure leaves them unpriced, never fails the search."""
    try:
        live = age_rated_premiums(
            [p.hios_plan_id for p in plans],
            age=age, state=county.state, countyfips=county.fips, zipcode=zip_code, year=year,
        )
    except (requests.RequestException, ValueError, MarketplaceApiKeyMissingError) as exc:
        # The exception text is method and path only (see core.marketplace_api).
        logger.warning("live premiums unavailable, showing reference premiums: %s", exc)
        live = {}
    return [replace(p, monthly_premium=live.get(p.hios_plan_id)) for p in plans]


def search_plans(session, *, zip_code: str, age: int, county_fips: str | None = None,
                 filters: PlanFilters | None = None) -> PlanSearchResult:
    filters = filters or PlanFilters()
    year, counties = _counties_for_zip(session, zip_code)
    if not counties:
        return PlanSearchResult("zip_not_found")

    # 126 ZIPs cross a state line, so a ZIP can be partly in a marketplace state.
    served = [c for c in counties if c.state in MARKETPLACE_STATES]
    if not served:
        return PlanSearchResult("not_marketplace_state", state=counties[0].state)

    chosen = next((c for c in served if c.fips == county_fips), None)
    if chosen is None:
        if len(served) > 1:
            # Plans and prices differ by county; merging them would list plans
            # the user cannot buy. The model is told to ask which one.
            return PlanSearchResult("ambiguous_county", counties=tuple(served), plan_year=year)
        chosen = served[0]

    loaded = session.scalar(
        select(exists().where(PlanCounty.countyfips == chosen.fips, PlanCounty.plan_id == Plan.id,
                              Plan.plan_year == year))
    )
    if not loaded:
        return PlanSearchResult("county_not_loaded", county=chosen, plan_year=year)

    excluded = filters.metal_level is None and age > _CATASTROPHIC_MAX_AGE
    if excluded:
        filters = replace(filters, include_catastrophic=False)

    candidates, total = find_plans(session, countyfips=chosen.fips, year=year, filters=filters,
                                   limit=MAX_PREMIUM_BATCH)
    if not candidates:
        return PlanSearchResult("no_match", county=chosen, plan_year=year, catastrophic_excluded=excluded)

    priced = _price(candidates, age=age, county=chosen, zip_code=zip_code, year=year)
    if filters.sort_by == "premium":
        # Live-priced plans by their real premium; any CMS did not price keep
        # their catalog order after them. sorted() is stable.
        priced = sorted(priced, key=lambda p: (not p.premium_is_live, p.monthly_premium or 0))

    shown = tuple(priced[:SHOWN_PLANS])
    logger.info("plan search: %d of %d plans shown, %d live-priced",
                len(shown), total, sum(p.premium_is_live for p in shown))
    return PlanSearchResult("ok", plans=shown, total_matching=total, plan_year=year, county=chosen,
                            catastrophic_excluded=excluded)
