"""Reading CMS's California state-based exchange PUF (ADR 0024). No database."""
from decimal import Decimal

import pytest

from src.ingestion.ca_puf.read import (
    NO_CSR,
    PufFormatError,
    age_key,
    puf_money,
    read_puf,
)
from tests.ca_puf_fixtures import YEAR, area_row, plan_row, rate_row, write_puf

BASE = "40513CA0010001"


def _read(tmp_path, plans=None, rates=None, areas=None, **kwargs):
    path = write_puf(
        tmp_path,
        plans=plans or [plan_row(f"{BASE}-01")],
        rates=rates or [rate_row(BASE, 16, "40", "512.34")],
        areas=areas or [area_row("Los Angeles - 06037")],
        **kwargs,
    )
    return read_puf(path, YEAR)


@pytest.mark.parametrize("text, amount", [
    ("$5,200 ", Decimal(5200)), ("$0", Decimal(0)), ("412.55", Decimal("412.55")),
    ("$1,234.56", Decimal("1234.56")), ("", None), ("  ", None), ("Not Applicable", None),
])
def test_money_is_read_as_cms_writes_it(text, amount):
    assert puf_money(text) == amount


@pytest.mark.parametrize("text", ["20% coinsurance", "$", "-5", "No Charge"])
def test_text_that_is_not_money_is_refused(text):
    with pytest.raises(PufFormatError, match="not an amount"):
        puf_money(text)


@pytest.mark.parametrize("text, age", [("0-14", 14), ("15", 15), ("63", 63), ("64 and over", 64)])
def test_age_bands_become_ages(text, age):
    assert age_key(text) == age


@pytest.mark.parametrize("text", ["14", "64", "65", "0-20", "adult"])
def test_an_unknown_age_band_is_refused(text):
    with pytest.raises(PufFormatError, match="unknown age band"):
        age_key(text)


def test_only_individual_on_exchange_medical_plans_are_kept(tmp_path):
    puf = _read(tmp_path, plans=[
        plan_row(f"{BASE}-01"),
        plan_row("40513CA0010002-01", market="SHOP (Small Group)"),
        plan_row("40513CA0010003-01", dental="Yes"),
        plan_row("40513CA0010004-01", qhp="Off the Exchange"),
        plan_row("40513CA0010005-00"),
    ])

    assert [p.hios_plan_id for p in puf.plans] == [BASE]
    assert puf.label == "01011999"


def test_a_plan_comes_from_its_standard_variant_and_expanded_bronze_is_kept(tmp_path):
    bronze = "40513CA0020001"
    puf = _read(tmp_path, plans=[
        plan_row(f"{bronze}-01", metal="Expanded Bronze", name=" Bronze 60 HMO ", hsa="Yes",
                 variant="Standard Bronze On Exchange Plan"),
    ], rates=[rate_row(bronze, 16, "40", "400.00")])

    (plan,) = puf.plans
    assert (plan.hios_plan_id, plan.metal_level, plan.marketing_name, plan.issuer_id, plan.service_area_id,
            plan.hsa_eligible, plan.has_national_network) == (
        bronze, "Expanded Bronze", "Bronze 60 HMO", "40513", "CAS001", True, False)


def test_cost_shares_use_the_apis_words_and_an_empty_column_is_no_row(tmp_path):
    puf = _read(tmp_path, plans=[
        plan_row(f"{BASE}-01", medical="$2,000 ", drug="$250", moop="$9,200 "),
        plan_row(f"{BASE}-06", variant="94% AV Level Silver Plan", medical="$0", drug="$0", moop="$1,400"),
    ])

    shares = {(s.csr_variant, s.kind, s.cost_share_type): s.amount for s in puf.cost_shares}
    assert shares == {
        (NO_CSR, "deductible", "Medical EHB Deductible"): Decimal(2000),
        (NO_CSR, "deductible", "Drug EHB Deductible"): Decimal(250),
        (NO_CSR, "moop", "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"): Decimal(9200),
        ("94% AV Level Silver Plan", "deductible", "Medical EHB Deductible"): Decimal(0),
        ("94% AV Level Silver Plan", "deductible", "Drug EHB Deductible"): Decimal(0),
        ("94% AV Level Silver Plan", "moop", "Maximum Out of Pocket for Medical and Drug EHB Benefits (Total)"):
            Decimal(1400),
    }
    assert {s.hios_plan_id for s in puf.cost_shares} == {BASE}


def test_a_combined_deductible_is_read_when_the_plan_has_one(tmp_path):
    puf = _read(tmp_path, plans=[plan_row(f"{BASE}-01", combined="$7,200", medical="", drug="")])

    assert [(s.cost_share_type, s.amount) for s in puf.cost_shares if s.kind == "deductible"] == [
        ("Combined Medical and Drug EHB Deductible", Decimal(7200))]


def test_a_base_plan_with_no_standard_variant_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="no -01 row"):
        _read(tmp_path, plans=[plan_row(f"{BASE}-06", variant="94% AV Level Silver Plan")])


def test_a_plan_id_out_of_shape_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="unexpected plan id"):
        _read(tmp_path, plans=[plan_row("40513TX0010001-01")])


def test_a_yes_no_column_with_anything_else_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="Yes or No"):
        _read(tmp_path, plans=[plan_row(f"{BASE}-01", hsa="Y")])


def test_service_areas_carry_county_zips_and_statewide_rows(tmp_path):
    puf = _read(tmp_path, areas=[
        area_row("Los Angeles - 06037", partial="90002, 90001, 90002"),
        area_row("Orange - 06059"),
        area_row("", statewide="true", area="CAS002"),
        area_row("Orange - 06059", market="SHOP (Small Group)"),
        area_row("Orange - 06059", dental="Yes"),
    ])

    assert [(a.countyfips, a.zipcodes, a.service_area_id) for a in puf.service_areas] == [
        ("06037", ("90001", "90002"), "CAS001"),
        ("06059", None, "CAS001"),
        (None, None, "CAS002"),
    ]


@pytest.mark.parametrize("area, message", [
    (area_row("Somewhere"), "unexpected county"),
    (area_row("Clark - 32003"), "unexpected county"),
    (area_row("Los Angeles - 06037", partial="9001, abcde"), "bad ZIP list"),
])
def test_a_service_area_out_of_shape_is_refused(tmp_path, area, message):
    with pytest.raises(PufFormatError, match=message):
        _read(tmp_path, areas=[area])


def test_rates_are_kept_only_for_kept_plans(tmp_path):
    puf = _read(tmp_path, rates=[
        rate_row(BASE, 16, "0-14", "300.00"),
        rate_row(BASE, 16, "64 and over", "1200.00"),
        rate_row("62683CA0010001", 16, "40", "30.00"),  # a dental plan's
    ])

    assert puf.rates == {(BASE, 16, 14): Decimal("300.00"), (BASE, 16, 64): Decimal("1200.00")}


@pytest.mark.parametrize("rates, message", [
    ([rate_row(BASE, 16, "40", "")], "empty rate"),
    ([{**rate_row(BASE, 16, "40", "1.00"), "RATING AREA ID": "Area 16"}], "unexpected rating area"),
    ([rate_row(BASE, 16, "40", "1.00"), rate_row(BASE, 16, "40", "2.00")], "two rates"),
])
def test_a_rate_out_of_shape_is_refused(tmp_path, rates, message):
    with pytest.raises(PufFormatError, match=message):
        _read(tmp_path, rates=rates)


def test_a_file_for_another_year_or_state_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="plan year 2025"):
        _read(tmp_path, plans=[plan_row(f"{BASE}-01", year=2025)])

    row = {**plan_row(f"{BASE}-01"), "STATE CODE": "NV"}
    with pytest.raises(PufFormatError, match="in NV"):
        _read(tmp_path, plans=[row])


def test_a_missing_column_is_named(tmp_path):
    row = plan_row(f"{BASE}-01")
    del row["PLAN MARKETING NAME"]

    with pytest.raises(PufFormatError, match="PLAN MARKETING NAME"):
        _read(tmp_path, plans=[row])


def test_a_zip_missing_a_file_or_mixing_dates_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="no CARates file"):
        _read(tmp_path, names={"Rates": None})
    with pytest.raises(PufFormatError, match="different dates"):
        _read(tmp_path, names={"Rates": "CARates02021999.csv"})


def test_a_file_with_no_individual_on_exchange_medical_plans_is_refused(tmp_path):
    with pytest.raises(PufFormatError, match="no individual, on-exchange medical plans"):
        _read(tmp_path, plans=[plan_row(f"{BASE}-01", qhp="Both")])
