"""The filed-rate catalog tables (ADR 0024). Real Postgres; plan year 1999."""
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.plan import CatalogLoad, Issuer, Plan, PlanCounty, PlanRate, RatingArea


def _issuer(session, hios="99999", state="CA"):
    issuer = Issuer(hios_issuer_id=hios, plan_year=1999, name="Test", state=state)
    session.add(issuer)
    session.flush()
    return issuer


def _plan(session, issuer, plan_id="99999CA0010001", **fields):
    plan = Plan(issuer_id=issuer.id, hios_plan_id=plan_id, plan_year=1999, marketing_name="P",
                metal_level="Silver", plan_type="HMO", state=issuer.state, hsa_eligible=False,
                has_national_network=False, **fields)
    session.add(plan)
    session.flush()
    return plan


def test_a_plan_defaults_to_the_api_catalog(session):
    plan = _plan(session, _issuer(session, "99998", "TX"), "99998TX0010001")
    session.refresh(plan)

    assert plan.catalog_source == "cms_api"


def test_a_plan_accepts_only_a_known_catalog_source(session):
    issuer = _issuer(session)
    assert _plan(session, issuer, catalog_source="ca_sbe_puf").catalog_source == "ca_sbe_puf"

    with pytest.raises(IntegrityError, match="ck_plans_catalog_source"), session.begin_nested():
        _plan(session, issuer, "99999CA0010002", catalog_source="scraped")


def test_a_plan_county_may_be_limited_to_some_zips(session):
    plan = _plan(session, _issuer(session), catalog_source="ca_sbe_puf")
    session.add_all([PlanCounty(plan_id=plan.id, countyfips="06037", zipcodes=["90001", "90002"]),
                     PlanCounty(plan_id=plan.id, countyfips="06059")])
    session.flush()

    rows = {c.countyfips: c.zipcodes for c in session.query(PlanCounty).filter_by(plan_id=plan.id)}
    assert rows == {"06037": ["90001", "90002"], "06059": None}


def test_a_rate_is_one_per_plan_area_and_age_and_ages_run_14_to_64(session):
    plan = _plan(session, _issuer(session), catalog_source="ca_sbe_puf")
    session.add(PlanRate(plan_id=plan.id, rating_area=16, age=40, individual_rate=Decimal("512.34")))
    session.flush()

    with pytest.raises(IntegrityError, match="uq_plan_rates"), session.begin_nested():
        session.add(PlanRate(plan_id=plan.id, rating_area=16, age=40, individual_rate=Decimal(1)))
        session.flush()
    for age in (13, 65):
        with pytest.raises(IntegrityError, match="ck_plan_rates_age"), session.begin_nested():
            session.add(PlanRate(plan_id=plan.id, rating_area=16, age=age, individual_rate=Decimal(1)))
            session.flush()


def test_rates_and_counties_leave_with_their_plan(session):
    plan = _plan(session, _issuer(session), catalog_source="ca_sbe_puf")
    session.add_all([PlanRate(plan_id=plan.id, rating_area=1, age=14, individual_rate=Decimal("300.00")),
                     PlanCounty(plan_id=plan.id, countyfips="06003")])
    session.flush()
    plan_id = plan.id

    session.delete(plan)
    session.flush()

    assert session.query(PlanRate).filter_by(plan_id=plan_id).count() == 0
    assert session.query(PlanCounty).filter_by(plan_id=plan_id).count() == 0


def test_a_rating_area_row_is_unique_per_year_county_and_zip_prefix(session):
    session.add_all([RatingArea(state="CA", plan_year=1999, countyfips="06037", zip3="900", rating_area=16),
                     RatingArea(state="CA", plan_year=1999, countyfips="06059", rating_area=18)])
    session.flush()
    # The whole county is '', never NULL, so the unique key holds for it too.
    assert session.query(RatingArea).filter_by(plan_year=1999, countyfips="06059").one().zip3 == ""

    with pytest.raises(IntegrityError, match="uq_rating_areas"), session.begin_nested():
        session.add(RatingArea(state="CA", plan_year=1999, countyfips="06059", rating_area=17))
        session.flush()


def test_a_load_is_recorded_with_when_it_ran(session):
    session.add(CatalogLoad(source="ca_sbe_puf", state="CA", plan_year=1999, file_url="file:test.zip",
                            file_label="01011999", sha256="0" * 64, plans=1))
    session.flush()

    assert session.query(CatalogLoad).filter_by(plan_year=1999).one().loaded_at is not None
