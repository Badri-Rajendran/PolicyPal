"""Loading a California PUF into the catalog (ADR 0024). Real Postgres, plan year 1999.

Real California county FIPS, because the rating-area map is keyed by them;
plan year 1999 keeps a locally loaded 2026 catalog out of every query.
"""
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.ingestion.ca_puf import __main__ as cli
from src.ingestion.ca_puf.download import NotPublishedError
from src.ingestion.ca_puf.load import LoadError, load, sold_counties
from src.ingestion.ca_puf.read import read_puf
from src.ingestion.marketplace_api import County
from src.ingestion.plans import _write_zip_counties
from src.models.plan import (
    CatalogLoad,
    Issuer,
    Plan,
    PlanCostShare,
    PlanCounty,
    PlanRate,
    RatingArea,
)
from tests.ca_puf_fixtures import YEAR, area_row, plan_row, rate_row, write_puf

KAISER = "40513CA0010001"
WHA_NORTH = "93689CA0110001"  # rated in area 2 only
WHA_SAC = "93689CA0150001"  # rated in area 3 only
LA_16 = ("90001", "90002")
LA_15 = ("90601",)
LA_UNLISTED = ("90134",)
COUNTIES = {"06037": LA_16 + LA_15 + LA_UNLISTED, "06041": ("94901",), "06067": ("95814",)}
_MODELS = (Plan, PlanCounty, PlanCostShare, PlanRate, RatingArea)


def _crosswalk(session):
    """1999: Los Angeles (both areas and an unlisted prefix), Marin (area 2),
    Sacramento (area 3), and a Texas county to prove it is untouched."""
    _write_zip_counties(session, [
        County("CA", "06037", "Los Angeles", LA_16 + LA_15 + LA_UNLISTED),
        County("CA", "06041", "Marin", ("94901",)),
        County("CA", "06067", "Sacramento", ("95814",)),
        County("TX", "48001", "Anderson", ("75801",)),
    ], YEAR)


def _file(tmp_path, *, plans=None, rates=None, areas=None):
    plans = plans or [
        plan_row(f"{KAISER}-01"),
        plan_row(f"{KAISER}-06", variant="94% AV Level Silver Plan", medical="$0", drug="$0", moop="$1,400"),
        plan_row(f"{WHA_NORTH}-01", issuer="93689"),
        plan_row(f"{WHA_SAC}-01", issuer="93689"),
    ]
    rates = rates or [
        rate_row(KAISER, 16, "40", "500.00"), rate_row(KAISER, 15, "40", "480.00"),
        rate_row(WHA_NORTH, 2, "40", "450.00"), rate_row(WHA_SAC, 3, "40", "440.00"),
    ]
    areas = areas or [
        area_row("Los Angeles - 06037"),
        area_row("Marin - 06041", issuer="93689"), area_row("Sacramento - 06067", issuer="93689"),
    ]
    return read_puf(write_puf(tmp_path, plans=plans, rates=rates, areas=areas), YEAR)


def _load(session, puf):
    return load(session, puf, year=YEAR, file_url="file:test.zip", sha256="a" * 64)


def _counts(session):
    return [session.query(model).count() for model in _MODELS]


def test_a_plan_is_sold_only_where_it_has_a_rate(tmp_path):
    """Western Health Advantage files one service area over two rating areas, with a plan per area."""
    sold, dropped = sold_counties(_file(tmp_path), COUNTIES)

    assert sold[WHA_NORTH] == {"06041": None}
    assert sold[WHA_SAC] == {"06067": None}
    assert dropped == 2
    # Rated in both Los Angeles areas: the whole county.
    assert sold[KAISER] == {"06037": None}


def test_in_los_angeles_a_plan_keeps_the_zips_of_its_rated_area_and_those_with_none(tmp_path):
    puf = _file(tmp_path, plans=[plan_row(f"{KAISER}-01")], rates=[rate_row(KAISER, 16, "40", "500.00")],
                areas=[area_row("Los Angeles - 06037")])

    sold, _ = sold_counties(puf, COUNTIES)

    assert sold[KAISER] == {"06037": ("90001", "90002", "90134")}


def test_a_partial_county_keeps_its_zips_and_a_whole_county_row_wins(tmp_path):
    puf = _file(tmp_path, plans=[plan_row(f"{WHA_NORTH}-01", issuer="93689")],
                rates=[rate_row(WHA_NORTH, 2, "40", "450.00")],
                areas=[area_row("Marin - 06041", issuer="93689", partial="94901")])
    partial, _ = sold_counties(puf, COUNTIES)
    assert partial[WHA_NORTH] == {"06041": ("94901",)}

    both = _file(tmp_path, plans=[plan_row(f"{WHA_NORTH}-01", issuer="93689")],
                 rates=[rate_row(WHA_NORTH, 2, "40", "450.00")],
                 areas=[area_row("Marin - 06041", issuer="93689", partial="94901"),
                        area_row("Marin - 06041", issuer="93689")])
    whole, _ = sold_counties(both, COUNTIES)
    assert whole[WHA_NORTH] == {"06041": None}


def test_a_statewide_service_area_covers_every_county_the_plan_is_rated_in(tmp_path):
    puf = _file(tmp_path, plans=[plan_row(f"{KAISER}-01", area="CAS009")],
                rates=[rate_row(KAISER, 2, "40", "1.00"), rate_row(KAISER, 3, "40", "1.00")],
                areas=[area_row("", statewide="true", area="CAS009")])

    sold, dropped = sold_counties(puf, COUNTIES)

    assert sold[KAISER] == {"06041": None, "06067": None}
    assert dropped == 1  # Los Angeles: no rate in area 15 or 16


def test_loading_writes_the_catalog_and_loading_again_changes_nothing(tmp_path, session):
    _crosswalk(session)
    puf = _file(tmp_path)

    first = _load(session, puf)
    counts = _counts(session)
    again = _load(session, puf)

    assert (first.plans, first.issuers, first.dropped_unrated, first.unrated_zips) == (3, 2, 2, ("90134",))
    assert _counts(session) == counts
    assert again == first
    kaiser = session.scalar(select(Plan).where(Plan.hios_plan_id == KAISER, Plan.plan_year == YEAR))
    assert (kaiser.catalog_source, kaiser.state, kaiser.premium_reference, kaiser.metal_level) == (
        "ca_sbe_puf", "CA", None, "Silver")
    assert session.scalar(select(Issuer.name).where(Issuer.hios_issuer_id == "40513", Issuer.plan_year == YEAR)) \
        == "Kaiser Permanente"
    assert session.scalar(select(PlanRate.individual_rate).where(
        PlanRate.plan_id == kaiser.id, PlanRate.rating_area == 15, PlanRate.age == 40)) == Decimal("480.00")
    shares = {(s.csr_variant, s.cost_share_type, s.network_tier, s.family_cost): s.amount
              for s in session.scalars(select(PlanCostShare).where(PlanCostShare.plan_id == kaiser.id))}
    assert shares[("Exchange variant (no CSR)", "Medical EHB Deductible", "In-Network", "Individual")] \
        == Decimal(2000)
    assert shares[("94% AV Level Silver Plan", "Medical EHB Deductible", "In-Network", "Individual")] == Decimal(0)
    assert session.query(CatalogLoad).filter_by(plan_year=YEAR, state="CA").count() == 2
    assert {(r.countyfips, r.zip3, r.rating_area) for r in session.scalars(
        select(RatingArea).where(RatingArea.plan_year == YEAR, RatingArea.countyfips != "06037"))} == {
        ("06041", "", 2), ("06067", "", 3)}


def test_a_plan_dropped_from_the_file_is_deleted_and_texas_is_untouched(tmp_path, session):
    _crosswalk(session)
    _load(session, _file(tmp_path))
    texas = Issuer(hios_issuer_id="11111", plan_year=YEAR, name="Texan", state="TX")
    session.add(texas)
    session.flush()
    session.add(Plan(issuer_id=texas.id, hios_plan_id="11111TX0010001", plan_year=YEAR, marketing_name="T",
                     metal_level="Silver", plan_type="HMO", state="TX", hsa_eligible=False,
                     has_national_network=False))
    session.flush()

    _load(session, _file(tmp_path, plans=[plan_row(f"{KAISER}-01")], rates=[rate_row(KAISER, 16, "40", "1.00")],
                         areas=[area_row("Los Angeles - 06037")]))

    left = set(session.scalars(select(Plan.hios_plan_id).where(Plan.plan_year == YEAR)))
    assert left == {KAISER, "11111TX0010001"}
    assert session.query(PlanRate).join(Plan).filter(Plan.hios_plan_id == WHA_NORTH, Plan.plan_year == YEAR).count() == 0


@pytest.mark.parametrize("change, message", [
    ({"plans": [plan_row("12345CA0010001-01", issuer="12345")],
      "rates": [rate_row("12345CA0010001", 16, "40", "1.00")]}, "issuer 12345"),
    ({"rates": [rate_row(KAISER, 16, "40", "1.00"), rate_row(WHA_NORTH, 2, "40", "1.00")]}, "no rates"),
    ({"rates": [rate_row(KAISER, 16, "40", "1.00"), rate_row(KAISER, 19, "40", "1.00"),
                rate_row(WHA_NORTH, 2, "40", "1.00"), rate_row(WHA_SAC, 3, "40", "1.00")]}, "area 19"),
    ({"rates": [rate_row(KAISER, 16, "40", "1.00"), rate_row(WHA_NORTH, 3, "40", "1.00"),
                rate_row(WHA_SAC, 3, "40", "1.00")],
      "areas": [area_row("Los Angeles - 06037"), area_row("Marin - 06041", issuer="93689")]}, "sold in no county"),
    ({"areas": [area_row("Los Angeles - 06037"), area_row("Marin - 06041", issuer="93689"),
                area_row("Orange - 06059", issuer="93689")]}, "06059"),
])
def test_a_file_that_breaks_a_rule_writes_nothing(tmp_path, session, change, message):
    _crosswalk(session)

    with pytest.raises(LoadError, match=message):
        _load(session, _file(tmp_path, **change))

    assert session.query(Plan).filter(Plan.plan_year == YEAR).count() == 0
    assert session.query(RatingArea).filter(RatingArea.plan_year == YEAR).count() == 0
    assert session.query(CatalogLoad).filter(CatalogLoad.plan_year == YEAR).count() == 0


def test_a_county_missing_from_the_rating_area_map_writes_nothing(tmp_path, session):
    _crosswalk(session)
    _write_zip_counties(session, [County("CA", "06037", "Los Angeles", LA_16),
                                  County("CA", "06999", "Nowhere", ("99999",))], YEAR)

    with pytest.raises(LoadError, match="06999"):
        _load(session, _file(tmp_path, plans=[plan_row(f"{KAISER}-01")],
                             rates=[rate_row(KAISER, 16, "40", "1.00")], areas=[area_row("Los Angeles - 06037")]))
    assert session.query(Plan).filter(Plan.plan_year == YEAR).count() == 0


def test_without_a_crosswalk_for_the_year_nothing_is_loaded(tmp_path, session):
    with pytest.raises(LoadError, match="ZIP-to-county crosswalk"):
        _load(session, _file(tmp_path))


def test_the_command_exits_3_when_cms_has_not_published_the_year(capsys):
    with patch.object(cli, "download", side_effect=NotPublishedError("CMS has not published the 2031 file")), \
         pytest.raises(SystemExit) as exit_:
        cli.main(["--year", "2031"])

    assert exit_.value.code == cli.NOT_PUBLISHED
    assert "2031" in capsys.readouterr().out


def test_the_command_reports_a_bad_file_without_a_traceback(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK")
    with patch.object(cli, "read_puf", side_effect=cli.PufFormatError("the zip has no CAPlans file")), \
         pytest.raises(SystemExit) as exit_:
        cli.main(["--year", "1999", "--zip", str(bad)])

    assert "California plans not loaded: the zip has no CAPlans file" in str(exit_.value.code)


def test_the_command_refuses_a_source_the_registry_does_not_enable():
    with patch.object(cli, "require_enabled", side_effect=cli.SourceNotApprovedError("cms_ca_sbe_puf is disabled")), \
         patch.object(cli, "download") as download, pytest.raises(SystemExit) as exit_:
        cli.main(["--year", "2026"])

    download.assert_not_called()
    assert "disabled" in str(exit_.value.code)


def _in(session):
    """get_session for the command, bound to the test's rolled-back transaction."""
    @contextmanager
    def get_session():
        yield session
        session.flush()
    return get_session


def _zip(tmp_path):
    return write_puf(tmp_path, plans=[plan_row(f"{KAISER}-01")], rates=[rate_row(KAISER, 16, "40", "500.00")],
                     areas=[area_row("Los Angeles - 06037")], label="05051999")


def test_the_command_loads_a_hand_downloaded_file_and_says_what_it_loaded(tmp_path, session, capsys):
    _crosswalk(session)

    with patch.object(cli, "get_session", _in(session)), patch.object(cli, "county_zips") as fetch:
        cli.main(["--year", str(YEAR), "--zip", str(_zip(tmp_path))])

    fetch.assert_not_called()  # the crosswalk was already there
    out = capsys.readouterr().out
    assert "1 plans from 1 issuers, file 05051999" in out
    assert "shown unpriced: 90134" in out
    load_row = session.scalars(select(CatalogLoad).where(CatalogLoad.plan_year == YEAR)).one()
    assert (load_row.file_url, load_row.file_label, len(load_row.sha256)) == ("file:ca.zip", "05051999", 64)


def test_the_command_fetches_the_crosswalk_when_the_year_has_none(tmp_path, session, capsys):
    crosswalk = [County("CA", "06037", "Los Angeles", LA_16)]

    with patch.object(cli, "get_session", _in(session)), \
         patch.object(cli, "county_zips", return_value=crosswalk) as fetch:
        cli.main(["--year", str(YEAR), "--zip", str(_zip(tmp_path))])

    fetch.assert_called_once_with(YEAR)
    out = capsys.readouterr().out
    assert "fetching CMS's" in out and "2 ZIP-to-county pairs recorded" in out
    assert "unpriced" not in out


def test_the_command_downloads_the_published_file_when_given_no_zip(tmp_path, session):
    _crosswalk(session)
    path = _zip(tmp_path)

    with patch.object(cli, "get_session", _in(session)), \
         patch.object(cli, "download", return_value=path) as download:
        cli.main(["--year", str(YEAR), "--refresh"])

    download.assert_called_once_with(YEAR, refresh=True)
    assert session.scalars(select(CatalogLoad.file_url).where(CatalogLoad.plan_year == YEAR)).one() == (
        "https://www.cms.gov/files/zip/californiasbpuf1999.zip")


def test_the_command_says_when_it_needs_the_cms_key_for_the_crosswalk(tmp_path, session):
    with patch.object(cli, "get_session", _in(session)), \
         patch.object(cli, "county_zips", side_effect=cli.MarketplaceApiKeyMissingError("CMS_MARKETPLACE_API_KEY is not set")), \
         pytest.raises(SystemExit) as exit_:
        cli.main(["--year", str(YEAR), "--zip", str(_zip(tmp_path))])

    assert "California plans not loaded: CMS_MARKETPLACE_API_KEY" in str(exit_.value.code)
    assert session.query(Plan).filter(Plan.plan_year == YEAR).count() == 0


def test_an_empty_file_changes_nothing(tmp_path, session):
    """NOT IN () matches every row: an empty plan list must never reach the delete."""
    _crosswalk(session)
    _load(session, _file(tmp_path))
    before = _counts(session)
    empty = replace(_file(tmp_path), plans=(), cost_shares=(), rates={})

    with pytest.raises(LoadError, match="no plans"):
        _load(session, empty)

    assert _counts(session) == before
