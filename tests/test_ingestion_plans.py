"""Plan catalog writes (docs/plans/phase-1-marketplace-api.md, Step 2).

The roadmap's acceptance criterion is that a re-run changes no row count.
These run against real Postgres through the `session` fixture, and use plan
year 1999 so a locally ingested catalog cannot skew the counts.
"""
from contextlib import contextmanager

import pytest
import requests
from sqlalchemy import func, select

from src.ingestion.plans import _write_county, execute, resolve_states
from src.models.plan import Issuer, Plan, PlanCostShare, PlanCounty

YEAR = 1999


def _share(cost_share_type, amount):
    return {
        "type": cost_share_type,
        "amount": amount,
        "csr": "Exchange variant (no CSR)",
        "network_tier": "In-Network",
        "family_cost": "Individual",
    }


def _plan(plan_id="11111TX0010001", premium=300.5, deductibles=None, rating=3, **overrides):
    plan = {
        "id": plan_id,
        "name": "Test Silver HMO",
        "metal_level": "Silver",
        "type": "HMO",
        "state": "TX",
        "premium": premium,
        "hsa_eligible": False,
        "has_national_network": False,
        "is_standardized_plan": True,
        "quality_rating": {"global_rating": rating, "global_not_rated_reason": ""},
        "issuer": {"id": "11111", "name": "Test Issuer", "state": "TX"},
        "deductibles": [_share("Combined Medical and Drug EHB Deductible", 2000)]
        if deductibles is None
        else deductibles,
        "moops": [_share("Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)", 9000)],
        "benefits_url": "https://example.test/sbc.pdf",
    }
    return plan | overrides


def _counts(session):
    in_year = select(Plan.id).where(Plan.plan_year == YEAR)
    return {
        "issuers": session.scalar(select(func.count()).select_from(Issuer).where(Issuer.plan_year == YEAR)),
        "plans": session.scalar(select(func.count()).select_from(Plan).where(Plan.plan_year == YEAR)),
        "plan_counties": session.scalar(
            select(func.count()).select_from(PlanCounty).where(PlanCounty.plan_id.in_(in_year))
        ),
        "plan_cost_shares": session.scalar(
            select(func.count()).select_from(PlanCostShare).where(PlanCostShare.plan_id.in_(in_year))
        ),
    }


def _deductibles(session, plan_id):
    return session.execute(
        select(PlanCostShare.cost_share_type, PlanCostShare.amount)
        .join(Plan, Plan.id == PlanCostShare.plan_id)
        .where(Plan.hios_plan_id == plan_id, Plan.plan_year == YEAR, PlanCostShare.kind == "deductible")
        .order_by(PlanCostShare.cost_share_type)
    ).all()


def test_a_rerun_changes_no_row_count(session):
    """The acceptance criterion. Plan B is sold in both counties, so it must
    stay one plan row with two county links, however many times it syncs."""
    county_a = [_plan("11111TX0010001"), _plan("11111TX0010002")]
    county_b = [_plan("11111TX0010002"), _plan("11111TX0010003")]

    _write_county(session, county_a, "48113", YEAR)
    _write_county(session, county_b, "48439", YEAR)
    first = _counts(session)

    _write_county(session, county_a, "48113", YEAR)
    _write_county(session, county_b, "48439", YEAR)

    assert first == {"issuers": 1, "plans": 3, "plan_counties": 4, "plan_cost_shares": 6}
    assert _counts(session) == first


def test_the_latest_sync_overwrites_values_in_place(session):
    _write_county(session, [_plan(premium=300.5)], "48113", YEAR)
    _write_county(
        session, [_plan(premium=312.75, deductibles=[_share("Combined Medical and Drug EHB Deductible", 2500)])],
        "48113", YEAR,
    )

    plan = session.scalars(select(Plan).where(Plan.plan_year == YEAR)).one()
    assert str(plan.premium_reference) == "312.75"
    assert [str(amount) for _, amount in _deductibles(session, plan.hios_plan_id)] == ["2500.00"]
    assert _counts(session)["plans"] == 1


def test_a_variant_dropped_upstream_is_removed(session):
    """Cost shares are replaced, not upserted — an upsert alone would keep a
    deductible the plan no longer has, with nothing to prune it by."""
    both = [_share("Medical EHB Deductible", 0), _share("Drug EHB Deductible", 5500)]
    _write_county(session, [_plan(deductibles=both)], "48113", YEAR)
    _write_county(session, [_plan(deductibles=both[:1])], "48113", YEAR)

    assert [t for t, _ in _deductibles(session, "11111TX0010001")] == ["Medical EHB Deductible"]


def test_a_medical_and_a_drug_deductible_are_both_kept(session):
    """Real plans carry both under an identical CSR/tier/family key (plan
    40220TX0080031: $0 medical, $5,500 drug). Without the type in the unique
    key one overwrites the other, and the plan reads as a $0 deductible."""
    both = [_share("Medical EHB Deductible", 0), _share("Drug EHB Deductible", 5500)]
    _write_county(session, [_plan(deductibles=both)], "48113", YEAR)

    assert [(t, str(a)) for t, a in _deductibles(session, "11111TX0010001")] == [
        ("Drug EHB Deductible", "5500.00"),
        ("Medical EHB Deductible", "0.00"),
    ]


def test_an_unrated_plan_is_stored_as_null_not_zero(session):
    """CMS reports "not rated" as 0 on a 1-5 scale. Stored as 0, every
    unrated plan would rank as the worst-rated."""
    _write_county(session, [_plan(rating=0)], "48113", YEAR)

    assert session.scalar(select(Plan.quality_rating_global).where(Plan.plan_year == YEAR)) is None


def test_an_incomplete_plan_is_skipped_without_blocking_the_rest(session):
    broken = _plan("11111TX0010009", metal_level=None)
    written, _ = _write_county(session, [broken, _plan("11111TX0010001")], "48113", YEAR)

    assert written == 1
    assert session.scalars(select(Plan.hios_plan_id).where(Plan.plan_year == YEAR)).all() == ["11111TX0010001"]


def test_one_failing_county_does_not_stop_the_run(session, monkeypatch, capsys):
    """A full run is hours of requests, unattended. One county's outage must be
    reported and skipped, never allowed to end the run for every state after it."""

    def county_plans(state, countyfips, zipcode, year):
        if countyfips == "48113":
            raise requests.ConnectionError("down")
        return [_plan("11111TX0010005")]

    @contextmanager
    def same_session():
        yield session

    monkeypatch.setattr("src.ingestion.plans.counties_by_state",
                        lambda year: {"TX": [("48113", "75001"), ("48439", "76101")]})
    monkeypatch.setattr("src.ingestion.plans.county_plans", county_plans)
    monkeypatch.setattr("src.ingestion.plans.get_session", same_session)

    execute(["TX"], YEAR)

    assert session.scalars(select(Plan.hios_plan_id).where(Plan.plan_year == YEAR)).all() == ["11111TX0010005"]
    assert "1 counties ingested, 1 failed" in capsys.readouterr().out


def test_resolve_states_normalizes_and_expands_all():
    assert resolve_states(" tx, FL ,tx") == ["TX", "FL"]
    assert len(resolve_states("all")) == 30


@pytest.mark.parametrize("raw", ["GA", "TX,IL", " , "])
def test_resolve_states_rejects_what_the_api_would(raw):
    """GA and IL run their own exchanges; the API answers them with a 400.
    Failing here costs nothing; failing there costs a request per county."""
    with pytest.raises(ValueError):
        resolve_states(raw)
