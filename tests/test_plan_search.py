"""Plan search over the catalog, priced live (ADR 0010).

Real Postgres through the `session` fixture; rows are written with the
ingestion writers, so they have the shape a real sync produces. Plan year
1999 and ZIPs 0000x keep a locally ingested catalog out of the results. CMS
is always patched.
"""
import logging
from decimal import Decimal
from unittest.mock import patch

import requests

from src.ingestion.marketplace_api import County
from src.ingestion.plans import _write_county, _write_zip_counties
from src.services.plan_search import PlanFilters, search_plans

YEAR = 1999
NO_CSR = "Exchange variant (no CSR)"


def _share(amount, csr=NO_CSR, cost_share_type="Combined Medical and Drug EHB Deductible"):
    return {"type": cost_share_type, "amount": amount, "csr": csr,
            "network_tier": "In-Network", "family_cost": "Individual"}


def _plan(plan_id, premium, metal_level="Silver", deductibles=None):
    return {
        "id": plan_id, "name": f"Plan {plan_id}", "metal_level": metal_level, "type": "HMO", "state": "TX",
        "premium": premium, "hsa_eligible": False, "has_national_network": False,
        "issuer": {"id": "11111", "name": "Test Issuer", "state": "TX"},
        "deductibles": deductibles or [_share(2000)],
        "moops": [_share(9000, cost_share_type="Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)")],
    }


def _catalog(session):
    """County 99001 sells A, B and a catastrophic plan; 99002 sells only C.
    ZIP 00001 lies in 99001 alone, 00002 in both counties, 00009 in Illinois."""
    _write_zip_counties(session, [
        County("TX", "99001", "Alpha", ("00001", "00002")),
        County("TX", "99002", "Beta", ("00002",)),
        County("IL", "99003", "Gamma", ("00009",)),
    ], YEAR)
    _write_county(session, [
        _plan("11111TX0010001", 300),
        _plan("11111TX0010002", 310),
        _plan("11111TX0010004", 200, metal_level="Catastrophic"),
    ], "99001", YEAR)
    _write_county(session, [_plan("11111TX0010003", 100)], "99002", YEAR)


def _search(session, zip_code="00001", age=34, live=None, **kwargs):
    with patch("src.services.plan_search.age_rated_premiums", return_value=live or {}) as cms:
        return search_plans(session, zip_code=zip_code, age=age, **kwargs), cms


def test_plans_are_the_countys_own_ordered_by_their_live_premium(session):
    """Premiums at the user's age can reorder plans — verified live, where
    issuers' age factors differed — so the live price decides the order."""
    _catalog(session)
    result, cms = _search(session, live={"11111TX0010001": Decimal("400.00"), "11111TX0010002": Decimal("390.00")})

    assert result.status == "ok"
    assert [p.hios_plan_id for p in result.plans] == ["11111TX0010002", "11111TX0010001"]
    assert [p.monthly_premium for p in result.plans] == [Decimal("390.00"), Decimal("400.00")]
    # What a saved card needs to say whose premium, and where, without the ZIP.
    assert {(p.premium_age, p.county_name, p.state) for p in result.plans} == {(34, "Alpha", "TX")}
    assert cms.call_args.kwargs == {
        "age": 34, "state": "TX", "countyfips": "99001", "zipcode": "00001", "year": YEAR
    }


def test_the_deductible_is_the_one_a_person_without_cost_sharing_reductions_pays(session):
    """A plan has a deductible per CSR variant; each is another population's.
    Mixing one in would misstate the plan, and filter it wrongly, for the
    people who pay the standard one."""
    _write_zip_counties(session, [County("TX", "99001", "Alpha", ("00001",))], YEAR)
    _write_county(session, [_plan("11111TX0010001", 300, deductibles=[
        _share(5000), _share(8000, csr="Limited Cost Sharing Plan Variation"),
    ])], "99001", YEAR)

    shown, _ = _search(session)
    filtered, _ = _search(session, filters=PlanFilters(max_deductible=6000))

    assert shown.plans[0].deductible == Decimal("5000.00")
    assert [p.hios_plan_id for p in filtered.plans] == ["11111TX0010001"]


def test_a_zip_in_two_counties_asks_which_one(session):
    """Merging the counties would list plans the user cannot buy."""
    _catalog(session)

    ambiguous, cms = _search(session, zip_code="00002")
    foreign, _ = _search(session, zip_code="00002", county_fips="99003")
    chosen, _ = _search(session, zip_code="00002", county_fips="99002")

    assert ambiguous.status == "ambiguous_county"
    assert [c.fips for c in ambiguous.counties] == ["99001", "99002"]
    cms.assert_not_called()
    # A county_fips must be one of the ZIP's own, or the model could point the query anywhere.
    assert foreign.status == "ambiguous_county"
    assert [p.hios_plan_id for p in chosen.plans] == ["11111TX0010003"]


def test_a_cms_outage_shows_catalog_prices_and_logs_no_personal_data(session, caplog):
    _catalog(session)
    with patch("src.services.plan_search.age_rated_premiums",
               side_effect=requests.RequestException("POST /plans failed: ReadTimeout")), \
         caplog.at_level(logging.DEBUG):
        result = search_plans(session, zip_code="00001", age=97)

    assert result.status == "ok"
    assert [p.hios_plan_id for p in result.plans] == ["11111TX0010001", "11111TX0010002"]
    assert not any(p.premium_is_live for p in result.plans)
    assert all(p.premium_age is None for p in result.plans)
    assert result.plans[0].premium_reference == Decimal("300.00")
    assert "00001" not in caplog.text
    assert "97" not in caplog.text


def test_catastrophic_plans_are_left_out_from_age_30_unless_asked_for(session):
    _catalog(session)

    older, _ = _search(session, age=30)
    younger, _ = _search(session, age=29)
    asked, _ = _search(session, age=45, filters=PlanFilters(metal_level="Catastrophic"))

    assert "11111TX0010004" not in [p.hios_plan_id for p in older.plans]
    assert older.catastrophic_excluded
    assert "11111TX0010004" in [p.hios_plan_id for p in younger.plans]
    assert [p.hios_plan_id for p in asked.plans] == ["11111TX0010004"]


def test_a_zip_outside_the_marketplace_states_is_named_as_such(session):
    _catalog(session)

    result, cms = _search(session, zip_code="00009")
    unknown, _ = _search(session, zip_code="00404")

    assert (result.status, result.state) == ("not_marketplace_state", "IL")
    assert unknown.status == "zip_not_found"
    cms.assert_not_called()


def test_mid_rollover_a_zip_uses_the_latest_year_its_county_is_loaded_for(session):
    """Next year's crosswalk covers every state as soon as any one is ingested
    for it. A ZIP whose county has no plans for that year yet must keep
    getting this year's, not "county not loaded"."""
    _catalog(session)
    _write_zip_counties(session, [County("TX", "99001", "Alpha", ("00001",)),
                                  County("TX", "99004", "Delta", ("00004",))], YEAR + 1)
    _write_county(session, [_plan("11111TX0010005", 100)], "99004", YEAR + 1)

    result, _ = _search(session, zip_code="00001")

    assert result.status == "ok"
    assert result.plan_year == YEAR
