"""California's SBC links: a hand-built manifest, checked, then applied (ADR 0026).

Real Postgres through the rolled-back `session` fixture, plan year 1999. The
carrier hosts are the made-up ones of the `sbc_hosts` fixture, except where
the committed manifest itself is checked against the committed registry.
"""
from contextlib import contextmanager
from datetime import date

import pytest
from sqlalchemy import select

from src.ingestion.ca_puf.load import CATALOG_SOURCE
from src.ingestion.sbc import manifest
from src.ingestion.sbc.manifest import (
    COLUMNS,
    ManifestError,
    apply_manifest,
    check,
    load_manifest,
    name_matches,
)
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcDocument

YEAR = 1999
GOLD, SILVER, BRONZE = "11111CA0010001", "11111CA0010002", "11111CA0010003"
HEADER = ",".join(COLUMNS)


def _write(tmp_path, *lines, header=HEADER):
    path = tmp_path / f"ca-{YEAR}.csv"
    path.write_text("\n".join([header, *lines]) + "\n", encoding="utf-8")
    return path


def _line(plan, url, year=YEAR, verified="2026-09-26", note="checked"):
    return f"{plan},{year},{url},{verified},{note}"


@pytest.fixture
def links(sbc_hosts):
    """One link per host, by host id."""
    return {id_: f"{prefix}{id_}.pdf" for id_, prefix in sbc_hosts.items()}


@pytest.fixture
def plans(session):
    """Three California plans loaded from the PUF, and one API-state plan with a link of its own."""
    issuer = Issuer(hios_issuer_id="11111", plan_year=YEAR, name="Example Care", state="CA")
    texas = Issuer(hios_issuer_id="22222", plan_year=YEAR, name="Texas Health", state="TX")
    session.add_all([issuer, texas])
    session.flush()
    for owner, plan_id, name, state, source, url in [
        (issuer, GOLD, "Gold 80 HMO", "CA", CATALOG_SOURCE, None),
        (issuer, SILVER, "Silver 70 HMO", "CA", CATALOG_SOURCE, None),
        (issuer, BRONZE, "Bronze 60 HMO", "CA", CATALOG_SOURCE, None),
        (texas, "22222TX0010001", "Texas Gold", "TX", "cms_api", "https://texas.example.com/sbc/own.pdf"),
    ]:
        session.add(Plan(issuer_id=owner.id, hios_plan_id=plan_id, plan_year=YEAR, marketing_name=name,
                         metal_level="Gold", plan_type="HMO", state=state, benefits_url=url,
                         hsa_eligible=False, has_national_network=False, catalog_source=source))
    session.flush()


def _links(session):
    return dict(session.execute(select(Plan.hios_plan_id, Plan.benefits_url).where(Plan.plan_year == YEAR)).all())


def _rows(tmp_path, *lines):
    return load_manifest(_write(tmp_path, *lines), YEAR)


# Loading: the file on its own, with no database

def test_a_valid_manifest_is_read_into_rows(tmp_path, links):
    rows = _rows(tmp_path, _line(GOLD, links["crawl"]), _line(SILVER, links["manual"], note=" "))

    assert rows == (manifest.ManifestRow(GOLD, links["crawl"], date(2026, 9, 26), "checked"),
                    manifest.ManifestRow(SILVER, links["manual"], date(2026, 9, 26), ""))


@pytest.mark.parametrize(("line", "message"), [
    (_line("11111CA001000", "{crawl}"), "is not a California base plan ID"),
    (_line("11111CA0010001-01", "{crawl}"), "is not a California base plan ID"),
    (_line("11111TX0010001", "{crawl}"), "is not a California base plan ID"),
    (_line(GOLD, "{crawl}", year=YEAR + 1), f"plan year '{YEAR + 1}' is not {YEAR}"),
    (_line(GOLD, "http://crawl.example.com/sbc/gold.pdf"), "the link is"),
    (_line(GOLD, "https://127.0.0.1/sbc/gold.pdf"), "the link is"),
    (_line(GOLD, "https://nobody.example.com/gold.pdf"), "no California sbc_host entry"),
    (_line(GOLD, "{texas}"), "no California sbc_host entry"),
    (_line(GOLD, "{crawl}", verified="26/09/2026"), "verified_on must be a date"),
    (_line(GOLD, "{crawl}") + ",extra", "expected 5 columns"),
    (f"{GOLD},{YEAR},{{crawl}}", "expected 5 columns"),
])
def test_a_bad_line_is_named_and_nothing_is_read(tmp_path, links, line, message):
    with pytest.raises(ManifestError, match=message) as error:
        _rows(tmp_path, _line(SILVER, links["crawl"]), line.format(**links))

    assert "line 3" in str(error.value)


def test_the_header_must_be_exactly_the_columns(tmp_path, links):
    with pytest.raises(ManifestError, match="the header must be"):
        load_manifest(_write(tmp_path, _line(GOLD, links["crawl"]), header="plan,year,url,verified,note"), YEAR)


def test_a_plan_listed_twice_is_refused(tmp_path, links):
    with pytest.raises(ManifestError, match=f"plan {GOLD} is listed more than once"):
        _rows(tmp_path, _line(GOLD, links["crawl"]), _line(GOLD, links["manual"]))


def test_a_file_that_is_not_utf8_is_a_manifest_error(tmp_path):
    path = tmp_path / "ca.csv"
    path.write_bytes(b"\xff\xfe" + HEADER.encode("utf-16-le"))

    with pytest.raises(ManifestError, match="could not be read"):
        load_manifest(path, YEAR)


def test_the_committed_2026_manifest_is_valid_against_the_committed_registry():
    """The file a person edits by hand; a bad row must fail here, not in a yearly run."""
    rows = load_manifest(manifest.manifest_path(2026), 2026)

    assert len(rows) == 114
    assert {row.hios_plan_id[:5] for row in rows} == {
        "18126", "27603", "40513", "51396", "70285", "84014", "92499", "92815", "93689"}


# Applying: the manifest decides every California plan's link

def test_applying_links_the_listed_plans_and_leaves_the_rest_with_none(tmp_path, session, plans, links):
    report = apply_manifest(session, _rows(tmp_path, _line(GOLD, links["crawl"]), _line(SILVER, links["crawl"])),
                            YEAR)

    assert _links(session) == {GOLD: links["crawl"], SILVER: links["crawl"], BRONZE: None,
                               "22222TX0010001": "https://texas.example.com/sbc/own.pdf"}
    assert report == manifest.ApplyReport(linked=2, documents=1, unlisted=(BRONZE,), disabled={})


def test_a_row_taken_out_of_the_manifest_takes_its_link_away(tmp_path, session, plans, links):
    apply_manifest(session, _rows(tmp_path, _line(GOLD, links["crawl"]), _line(SILVER, links["manual"])), YEAR)

    apply_manifest(session, _rows(tmp_path, _line(GOLD, links["crawl"])), YEAR)

    assert (_links(session)[GOLD], _links(session)[SILVER]) == (links["crawl"], None)


def test_a_disabled_carrier_is_unlinked_and_counted(tmp_path, session, plans, links):
    """Disabling its registry entry and applying again is how a carrier is removed."""
    report = apply_manifest(session, _rows(tmp_path, _line(GOLD, links["crawl"]), _line(SILVER, links["off"])), YEAR)

    assert _links(session)[SILVER] is None
    assert (report.linked, report.disabled) == (1, {"off": 1})


def test_a_plan_the_catalog_does_not_have_stops_the_apply(tmp_path, session, plans, links):
    before = _links(session)

    with pytest.raises(ManifestError, match="11111CA0010009 is in the manifest but not among"):
        apply_manifest(session, _rows(tmp_path, _line(GOLD, links["crawl"]), _line("11111CA0010009", links["crawl"])),
                       YEAR)

    assert _links(session) == before


def test_a_missing_manifest_applies_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path)

    assert manifest.apply_for_year(YEAR) is None


# Checking: what a person should look at after an ingest

@pytest.mark.parametrize(("name", "title", "matches"), [
    ("Silver 70 HMO", "Covered CA_Silver 70 HMO", True),
    ("Bronze 60 HDHP Premier HMO", "Sharp Health Plan: Sharp Bronze 60 Premier HDHP HMO", True),
    ("Gold 80 HMO", "Example Care: Gold 80 PPO", False),
    ("Gold 80 HMO", None, False),
])
def test_a_title_matches_when_it_prints_every_word_of_the_plans_name(name, title, matches):
    assert name_matches(name, title) is matches


def test_the_check_sorts_every_plan_into_what_it_needs(tmp_path, session, plans, links):
    issuer_id = session.scalar(select(Issuer.id).where(Issuer.hios_issuer_id == "11111"))
    for plan_id, name in (("11111CA0010004", "Platinum 90 HMO"), ("11111CA0010005", "Minimum Coverage HMO")):
        session.add(Plan(issuer_id=issuer_id, hios_plan_id=plan_id, plan_year=YEAR, marketing_name=name,
                         metal_level="Gold", plan_type="HMO", state="CA", hsa_eligible=False,
                         has_national_network=False, catalog_source=CATALOG_SOURCE))
    session.flush()
    wrong, blocked = f"{links['crawl']}?wrong", f"{links['crawl']}?blocked"
    apply_manifest(session, _rows(tmp_path, _line(GOLD, links["manual"]), _line(SILVER, wrong),
                                  _line(BRONZE, links["crawl"]), _line("11111CA0010004", blocked)), YEAR)
    session.add_all([
        SbcDocument(url=links["manual"], plan_year=YEAR, status="ok", title="Example Care: Gold 80 HMO",
                    acquisition="manual"),
        SbcDocument(url=wrong, plan_year=YEAR, status="ok", title="Example Care: Gold 80 HMO"),
        SbcDocument(url=blocked, plan_year=YEAR, status="blocked"),
    ])
    session.flush()

    report = check(session, YEAR)

    assert (report.read, report.manual) == (2, 1)
    assert report.name_mismatch == [("Example Care", SILVER, "Silver 70 HMO", "Example Care: Gold 80 HMO")]
    assert report.failed == [("Example Care", "11111CA0010004", "Platinum 90 HMO", "blocked")]
    assert report.not_read == [("Example Care", BRONZE, "Bronze 60 HMO")]
    assert report.no_link == [("Example Care", "11111CA0010005", "Minimum Coverage HMO")]
    assert report.awaiting_import == []


def test_an_unread_link_on_a_manual_host_is_awaiting_import(tmp_path, session, plans, links):
    apply_manifest(session, _rows(tmp_path, _line(GOLD, links["manual"])), YEAR)

    report = check(session, YEAR)

    assert report.awaiting_import == [("Example Care", GOLD, "Gold 80 HMO")]
    assert report.not_read == []


# The command

@pytest.fixture
def command(monkeypatch, session, tmp_path):
    @contextmanager
    def same_session():
        yield session
        session.flush()

    monkeypatch.setattr(manifest, "get_session", same_session)
    monkeypatch.setattr(manifest, "MANIFEST_DIR", tmp_path)


def test_the_apply_command_says_what_it_linked(command, tmp_path, session, plans, links, capsys):
    _write(tmp_path, _line(GOLD, links["crawl"]), _line(SILVER, links["off"]))

    manifest.main(["apply", "--year", str(YEAR)])

    out = capsys.readouterr().out
    assert f"1 California plans for {YEAR} linked to 1 SBC documents; 1 not in the manifest" in out
    assert "1 plans unlinked: registry entry off is disabled" in out


def test_the_apply_command_exits_with_the_broken_rule(command, tmp_path, plans, links):
    _write(tmp_path, _line(GOLD, "https://nobody.example.com/gold.pdf"))

    with pytest.raises(SystemExit, match="SBC manifest not applied: line 2"):
        manifest.main(["apply", "--year", str(YEAR)])


def test_the_apply_command_names_the_file_it_expected(command, tmp_path):
    with pytest.raises(SystemExit, match=f"No manifest for {YEAR}: expected .*ca-{YEAR}.csv"):
        manifest.main(["apply", "--year", str(YEAR)])


def test_the_check_command_prints_each_list_with_its_heading(command, tmp_path, session, plans, links, capsys):
    _write(tmp_path, _line(GOLD, links["manual"]))
    manifest.main(["apply", "--year", str(YEAR)])

    manifest.main(["check", "--year", str(YEAR)])

    out = capsys.readouterr().out
    assert f"California SBCs for {YEAR}: 0 plans read (0 from manual imports)" in out
    assert "Awaiting `make import-sbc`" in out and f"Example Care | {GOLD} | Gold 80 HMO" in out
    assert "No link in the manifest: 2" in out
