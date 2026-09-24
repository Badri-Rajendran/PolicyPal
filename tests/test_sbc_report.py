"""Coverage tracking: what has a Summary of Benefits, and what is missing (Phase 4).

Real Postgres through the rolled-back `session` fixture. The report is
read-only, which is checked here too: at this scale it is run often, and it
must never touch what it measures.
"""
import hashlib

import pytest
from sqlalchemy import func, select

from src.ingestion.sbc import report as sbc_report
from src.ingestion.sbc.report import collect, render
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.services.sbc_status import READ_STATUSES

YEAR = 1999
HCSC = "33602"      # in TOP_ISSUERS, under Health Care Service Corporation


@pytest.fixture
def catalog(session):
    """Two issuers in TX: one of a top parent, one on its own, with mixed statuses."""
    issuers = {
        HCSC: Issuer(hios_issuer_id=HCSC, plan_year=YEAR, name="BCBS of Texas", state="TX"),
        "99999": Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Small Health", state="TX"),
    }
    session.add_all(issuers.values())
    session.flush()

    def plan(issuer_id, plan_id, url, state="TX"):
        session.add(Plan(issuer_id=issuers[issuer_id].id, hios_plan_id=plan_id, plan_year=YEAR,
                         marketing_name=plan_id, metal_level="Silver", plan_type="HMO", state=state,
                         benefits_url=url, hsa_eligible=False, has_national_network=False))

    plan(HCSC, "33602TX0010001", "https://sbc.example.com/read.pdf")
    plan(HCSC, "33602TX0010002", "https://sbc.example.com/read.pdf")
    plan(HCSC, "33602TX0010003", "https://sbc.example.com/blocked.pdf")
    plan(HCSC, "33602TX0010004", "https://sbc.example.com/partial.pdf")
    plan("99999", "99999TX0010001", None)
    plan("99999", "99999TX0010002", "https://sbc.example.com/never-tried.pdf")
    plan("99999", "99999NH0010003", "https://sbc.example.com/read.pdf", state="NH")

    documents = (("read.pdf", "ok", None),
                 ("partial.pdf", "partial", "missing 2 of the 10 chart's groups"),
                 ("blocked.pdf", "blocked", "robots.txt disallows it"))
    for url, status, detail in documents:
        document = SbcDocument(url=f"https://sbc.example.com/{url}", plan_year=YEAR, status=status,
                               detail=detail, sha256=hashlib.sha256(url.encode()).hexdigest(),
                               parser_version=3)
        session.add(document)
        session.flush()
        if status in READ_STATUSES:
            session.add(SbcChunk(document_id=document.id, chunk_id=f"{url}#0", section="If you have a test",
                                 position=0, content="If you have a test\nImaging $100"))
    session.flush()


def _issuer_line(report, name):
    return next(coverage for (_, issuer), coverage in report.by_issuer.items() if issuer.startswith(name))


def _line_for(report, name):
    return next(line for line in render(report).splitlines() if line.strip().startswith(name))


def test_every_plan_is_counted_by_whether_its_document_was_read(session, catalog):
    report = collect(session, YEAR)

    assert (report.total.plans, report.total.read) == (7, 4)
    assert report.total.statuses == {"ok": 3, "partial": 1, "blocked": 1, "no_link": 1, "not_read": 1}
    assert report.by_state["TX"].plans == 6
    assert report.by_state["NH"].statuses == {"ok": 1}


def test_a_partly_read_document_counts_as_read(session, catalog):
    """`partial` text is stored, searched and quoted, so the report must not call it missing.

    Counting only `ok` made `make sbc-report` disagree with the plan card and
    the answer: it reported 1,918 of 3,276 plans covered where the rest of the
    app counted 1,940.
    """
    report = collect(session, YEAR)
    hcsc = _issuer_line(report, "BCBS of Texas")

    assert hcsc.read == 3                      # two `ok` plans and the `partial` one
    assert "partial" not in _line_for(report, "ALL")


def test_a_plan_with_no_link_and_one_never_read_are_both_counted(session, catalog):
    """Plans with no link were left out of ingestion's report entirely."""
    small = _issuer_line(collect(session, YEAR), "Small Health")

    assert small.statuses == {"no_link": 1, "not_read": 1, "ok": 1}


def test_an_issuer_is_shown_under_its_parent_company(session, catalog):
    parents = {parent for (parent, _) in collect(session, YEAR).by_issuer}

    assert parents == {"", "Health Care Service Corporation (BCBS TX, OK, MT)"}


def test_a_state_filter_counts_only_that_state(session, catalog):
    report = collect(session, YEAR, ["NH"])

    assert (report.total.plans, list(report.by_state)) == (1, ["NH"])


def test_why_each_document_could_not_be_read_is_counted(session, catalog):
    """A `partial` document was read, so it does not belong among the reasons it wasn't."""
    assert collect(session, YEAR).reasons == {("blocked", "robots.txt disallows it"): 1}


def test_a_document_no_plan_points_at_is_reported_as_an_orphan(session, catalog):
    session.add(SbcDocument(url="https://sbc.example.com/moved.pdf", plan_year=YEAR, status="ok"))
    session.flush()

    assert collect(session, YEAR).orphans == {"ok": 1}


def test_documents_stored_by_an_older_parser_are_counted(session, catalog):
    """Both read statuses: `_needs_reading` re-reads a `partial` document too."""
    session.execute(SbcDocument.__table__.update().values(parser_version=1))

    assert collect(session, YEAR).outdated == 2


def test_plans_the_latest_catalog_run_did_not_return_are_reported(session, catalog):
    """A withdrawn plan is reported, never removed: saved plan cards point at it."""
    old = session.scalar(select(func.min(Plan.updated_at)).where(Plan.plan_year == YEAR)) - sbc_report.STALE_AFTER * 2
    session.execute(Plan.__table__.update()
                    .where(Plan.hios_plan_id == "33602TX0010003").values(updated_at=old))

    assert collect(session, YEAR).stale_plans == {"TX": 1}


def test_the_report_writes_nothing(session, catalog):
    def snapshot():
        return (session.scalar(select(func.count()).select_from(Plan)),
                session.scalar(select(func.count()).select_from(SbcDocument)),
                session.scalar(select(func.max(SbcDocument.updated_at))))

    before = snapshot()
    render(collect(session, YEAR, verify=True))

    assert snapshot() == before


def test_kept_pdfs_are_counted_by_folder(session, catalog, monkeypatch, tmp_path):
    """Including the versions a refresh replaced: they are kept, so they take disk (ADR 0019)."""
    for folder, name in ((tmp_path / "raw", "kept"), (tmp_path / "rejected", "aside"),
                         (tmp_path / "archive", "replaced")):
        (folder / str(YEAR)).mkdir(parents=True)
        (folder / str(YEAR) / f"{name}.pdf").write_bytes(b"x" * 1024)
    monkeypatch.setattr(sbc_report, "SBC_RAW", tmp_path / "raw")
    monkeypatch.setattr(sbc_report, "SBC_REJECTED", tmp_path / "rejected")
    monkeypatch.setattr(sbc_report, "SBC_ARCHIVE", tmp_path / "archive")

    assert collect(session, YEAR).files == {"raw": (1, 1024), "rejected": (1, 1024), "archive": (1, 1024)}


def test_verifying_files_names_a_missing_one_and_one_whose_hash_changed(session, catalog, monkeypatch, tmp_path):
    monkeypatch.setattr(sbc_report, "cache_path", lambda url, year: tmp_path / f"{url.rsplit('/', 1)[1]}")
    (tmp_path / "read.pdf").write_bytes(b"a different file")
    (tmp_path / "partial.pdf").write_bytes(b"partial.pdf")   # the bytes its stored hash was taken from

    report = collect(session, YEAR, verify=True)

    assert (report.changed_files, report.missing_files) == (["https://sbc.example.com/read.pdf"], [])
    assert "files whose hash changed: 1" in render(report)


def test_verifying_files_checks_a_partly_read_documents_pdf_too(session, catalog, monkeypatch, tmp_path):
    """Its text is quoted in answers, so its kept PDF is worth the same check as any other."""
    monkeypatch.setattr(sbc_report, "cache_path", lambda url, year: tmp_path / f"{url.rsplit('/', 1)[1]}")
    (tmp_path / "read.pdf").write_bytes(b"read.pdf")

    report = collect(session, YEAR, verify=True)

    assert report.missing_files == ["https://sbc.example.com/partial.pdf"]
    assert report.changed_files == []
