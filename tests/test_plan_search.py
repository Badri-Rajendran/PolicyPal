"""Plan search over the catalog, priced live (ADR 0010).

Real Postgres through the `session` fixture; rows are written with the
ingestion writers, so they have the shape a real sync produces. Plan year
1999 and ZIPs 0000x keep a locally ingested catalog out of the results. CMS
is always patched.
"""
import logging
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import requests

from src.ingestion.marketplace_api import County
from src.ingestion.plans import _write_county, _write_zip_counties
from src.models.plan import Issuer, Plan, PlanCounty, PlanRate, RatingArea, ZipCounty
from src.models.sbc import SbcDocument
from src.services.plan_search import PlanFilters, rate_age, search_plans

YEAR = 1999
NO_CSR = "Exchange variant (no CSR)"


def _share(amount, csr=NO_CSR, cost_share_type="Combined Medical and Drug EHB Deductible"):
    return {"type": cost_share_type, "amount": amount, "csr": csr,
            "network_tier": "In-Network", "family_cost": "Individual"}


def _plan(plan_id, premium, metal_level="Silver", deductibles=None, benefits_url=None):
    return {
        "id": plan_id, "benefits_url": benefits_url, "name": f"Plan {plan_id}", "metal_level": metal_level, "type": "HMO", "state": "TX",
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


def test_each_plan_found_carries_whether_its_sbc_can_be_read(session):
    """ADR 0017: read, blocked, never read, or no link at all. Another year's
    document under the same link never makes a plan readable."""
    _write_zip_counties(session, [County("TX", "99001", "Alpha", ("00001",))], YEAR)
    urls = {plan_id: f"https://sbc.example.com/{plan_id}.pdf" for plan_id in ("11111TX0010001", "11111TX0010002",
                                                                               "11111TX0010003", "11111TX0010004")}
    _write_county(session, [
        _plan("11111TX0010001", 100, benefits_url=urls["11111TX0010001"]),
        _plan("11111TX0010002", 110, benefits_url=urls["11111TX0010002"]),
        _plan("11111TX0010003", 120, benefits_url=urls["11111TX0010003"]),
        _plan("11111TX0010004", 130, benefits_url=urls["11111TX0010004"]),
        _plan("11111TX0010005", 140),
    ], "99001", YEAR)
    session.add_all([
        SbcDocument(url=urls["11111TX0010001"], plan_year=YEAR, status="ok"),
        SbcDocument(url=urls["11111TX0010002"], plan_year=YEAR, status="blocked"),
        SbcDocument(url=urls["11111TX0010004"], plan_year=YEAR - 1, status="ok"),
    ])
    session.flush()

    result, _ = _search(session)

    assert result.total_matching == 5
    assert [(p.hios_plan_id, p.sbc_status) for p in result.plans] == [
        ("11111TX0010001", "ok"), ("11111TX0010002", "blocked"), ("11111TX0010003", "not_read"),
        ("11111TX0010004", "not_read"), ("11111TX0010005", "no_link"),
    ]


def test_a_bronze_search_includes_expanded_bronze(session):
    """Every California bronze plan, and many elsewhere, is "Expanded Bronze";
    asked for bronze, the user must see them, not "nothing matched"."""
    _write_zip_counties(session, [County("TX", "99001", "Alpha", ("00001",))], YEAR)
    _write_county(session, [
        _plan("11111TX0010001", 300, metal_level="Bronze"),
        _plan("11111TX0010002", 310, metal_level="Expanded Bronze"),
        _plan("11111TX0010003", 320, metal_level="Silver"),
    ], "99001", YEAR)

    bronze, _ = _search(session, filters=PlanFilters(metal_level="Bronze"))
    expanded, _ = _search(session, filters=PlanFilters(metal_level="Expanded Bronze"))

    assert [p.hios_plan_id for p in bronze.plans] == ["11111TX0010001", "11111TX0010002"]
    assert [p.hios_plan_id for p in expanded.plans] == ["11111TX0010002"]


# California (ADR 0024). A made-up county keeps a locally loaded 2026
# California catalog out: its rating areas come from the rating_areas table,
# never from the Python map, so fake FIPS and ZIPs work.
CA_COUNTY = "99101"
SILVER = "99999CA0010001"
BRONZE = "99999CA0010002"


def _ca_catalog(session, *, bronze_zips=None):
    """ZIP 00101 prices in area 16, 00601 in area 15, 00934 in none. Silver is
    sold in the whole county; Expanded Bronze only in `bronze_zips` if given.
    Silver's rate is 500 + age in area 16, 480 + age in 15; bronze's 100 less."""
    session.add_all([ZipCounty(zipcode=z, plan_year=YEAR, countyfips=CA_COUNTY, county_name="Angeles", state="CA")
                     for z in ("00101", "00601", "00934")])
    session.add_all([RatingArea(state="CA", plan_year=YEAR, countyfips=CA_COUNTY, zip3="001", rating_area=16),
                     RatingArea(state="CA", plan_year=YEAR, countyfips=CA_COUNTY, zip3="006", rating_area=15)])
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Kaiser Permanente", state="CA")
    session.add(issuer)
    session.flush()
    for plan_id, metal, zips, less in ((SILVER, "Silver", None, 0), (BRONZE, "Expanded Bronze", bronze_zips, 100)):
        plan = Plan(issuer_id=issuer.id, hios_plan_id=plan_id, plan_year=YEAR, marketing_name=f"{metal} 70 HMO",
                    metal_level=metal, plan_type="HMO", state="CA", hsa_eligible=False, has_national_network=False,
                    catalog_source="ca_sbe_puf")
        session.add(plan)
        session.flush()
        session.add(PlanCounty(plan_id=plan.id, countyfips=CA_COUNTY, zipcodes=zips))
        session.add_all([PlanRate(plan_id=plan.id, rating_area=area, age=age,
                                  individual_rate=Decimal(base + age - less))
                         for area, base in ((16, 500), (15, 480)) for age in (14, 29, 40, 64)])
    session.flush()


def _ca_search(session, zip_code="00101", age=40, on=date(1999, 9, 24), **kwargs):
    with patch("src.services.plan_search.age_rated_premiums") as cms, \
         patch("src.services.plan_search._today", return_value=on):
        return search_plans(session, zip_code=zip_code, age=age, **kwargs), cms


def test_california_is_priced_from_filed_rates_never_from_cms_live(session):
    _ca_catalog(session)

    result, cms = _ca_search(session)

    cms.assert_not_called()
    assert result.status == "ok"
    assert result.premium_source == "cms_filed_rates"
    assert [(p.hios_plan_id, p.monthly_premium) for p in result.plans] == [
        (BRONZE, Decimal(440)), (SILVER, Decimal(540))]
    assert {(p.premium_age, p.county_name, p.state) for p in result.plans} == {(40, "Angeles", "CA")}


def test_los_angeles_prices_each_zip_in_its_own_area(session):
    _ca_catalog(session)

    area_15, _ = _ca_search(session, zip_code="00601")

    assert [p.monthly_premium for p in area_15.plans] == [Decimal(420), Decimal(520)]


def test_a_zip_with_no_rating_area_is_shown_unpriced_never_guessed(session):
    _ca_catalog(session)

    result, cms = _ca_search(session, zip_code="00934")

    cms.assert_not_called()
    assert result.status == "ok"
    # Listed, since the plans are sold there; in plan-ID order, since none has a price.
    assert {p.hios_plan_id for p in result.plans} == {BRONZE, SILVER}
    assert all(p.monthly_premium is None and p.premium_age is None for p in result.plans)


def test_ages_outside_the_filed_bands_use_the_nearest_band_but_keep_the_persons_age(session):
    _ca_catalog(session)

    child, _ = _ca_search(session, age=10)
    older, _ = _ca_search(session, age=70)

    assert (rate_age(10), rate_age(14), rate_age(40), rate_age(64), rate_age(70)) == (14, 14, 40, 64, 64)
    assert child.plans[0].monthly_premium == Decimal(414)
    assert older.plans[0].monthly_premium == Decimal(464)
    assert (child.plans[0].premium_age, older.plans[0].premium_age) == (10, 70)


def test_an_age_with_no_filed_rate_is_unpriced_not_free(session):
    _ca_catalog(session)  # rates exist for 14, 29, 40 and 64 only

    result, _ = _ca_search(session, age=35)

    assert all(p.monthly_premium is None for p in result.plans)


def test_a_plan_sold_in_part_of_a_county_is_listed_only_for_its_zips(session):
    _ca_catalog(session, bronze_zips=["00601"])

    inside, _ = _ca_search(session, zip_code="00601")
    outside, _ = _ca_search(session, zip_code="00101")

    assert [p.hios_plan_id for p in inside.plans] == [BRONZE, SILVER]
    assert [p.hios_plan_id for p in outside.plans] == [SILVER]
    assert outside.total_matching == 1


def test_a_california_bronze_search_finds_expanded_bronze(session):
    _ca_catalog(session)

    result, _ = _ca_search(session, filters=PlanFilters(metal_level="Bronze"))

    assert [p.hios_plan_id for p in result.plans] == [BRONZE]


def test_sorting_by_deductible_still_breaks_ties_by_the_filed_premium(session):
    _ca_catalog(session)

    result, _ = _ca_search(session, filters=PlanFilters(sort_by="deductible"))

    # No cost shares: equal (null) deductibles, so the cheaper filed rate first.
    assert [p.hios_plan_id for p in result.plans] == [BRONZE, SILVER]


def test_in_open_enrollment_last_years_california_data_is_marked_prior_year(session):
    _ca_catalog(session)

    before, _ = _ca_search(session, on=date(1999, 10, 31))
    during, _ = _ca_search(session, on=date(1999, 11, 15))
    later, _ = _ca_search(session, on=date(2000, 3, 1))

    assert (before.prior_year, before.plan_year_on_sale) == (False, 1999)
    assert (during.prior_year, during.plan_year_on_sale) == (True, 2000)
    assert later.prior_year
    assert during.status == "ok" and during.plan_year == YEAR and during.plans


def test_nothing_matching_in_a_prior_year_still_says_so(session):
    _ca_catalog(session)

    result, _ = _ca_search(session, on=date(1999, 11, 15), filters=PlanFilters(metal_level="Platinum"))

    assert (result.status, result.prior_year, result.premium_source) == ("no_match", True, "cms_filed_rates")


def test_a_california_zip_before_any_california_load_names_its_exchange_state(session):
    _catalog(session)  # plans exist, none in California; it rewrites the year's crosswalk, so first
    session.add(ZipCounty(zipcode="00199", plan_year=YEAR, countyfips="99199", county_name="Nowhere", state="CA"))
    session.flush()

    result, cms = _ca_search(session, zip_code="00199")

    assert (result.status, result.state) == ("not_marketplace_state", "CA")
    cms.assert_not_called()


def test_a_california_search_logs_no_zip_or_age(session, caplog):
    _ca_catalog(session)

    with caplog.at_level(logging.DEBUG):
        _ca_search(session, zip_code="00601", age=57)

    assert "00601" not in caplog.text
    assert "57" not in caplog.text


def test_the_api_path_is_unchanged_and_says_it_is_live(session):
    _catalog(session)

    result, cms = _search(session, live={"11111TX0010001": Decimal("400.00")})

    cms.assert_called_once()
    assert (result.premium_source, result.prior_year) == ("cms_live", False)
