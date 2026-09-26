"""`make import-sbc`: reading an SBC a person downloaded in a browser (ADR 0026).

Real Postgres through the rolled-back `session` fixture; the real fetch cache,
pointed at a temporary folder, with the network replaced by a mock that
fails the test if anything asks it. The parser is the real one, fed
synthetic pages.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from src.ingestion.ca_puf.load import CATALOG_SOURCE
from src.ingestion.sbc import fetch, import_pdf, ingest
from src.ingestion.sbc.extract import (
    EVENT_HEADINGS,
    QUESTION_HEADINGS,
    PdfPage,
    TableRow,
    parse_sbc,
)
from src.ingestion.sbc.import_pdf import SbcImportError, import_file, import_folder
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument

YEAR = 1999
GOLD_PDF = b"%PDF-1.7 gold"


def _pages(test_cost="$60", year=YEAR):
    header = f"Coverage Period: 01/01/{year}-12/31/{year}\n: Example Gold | Coverage for: Individual"
    rows = [("Important Questions", "Answers | Why This Matters:")] + [
        (heading, "No.") for heading in QUESTION_HEADINGS] + [("Common Medical Event", "")] + [
        (heading, f"Imaging {test_cost} copay" if heading == "If you have a test" else "No charge")
        for heading in EVENT_HEADINGS]
    return [PdfPage(text=header, rows=tuple(TableRow(label, body) for label, body in rows))]


@pytest.fixture
def network(monkeypatch, tmp_path):
    """Any request at all fails the test: an import reads only what it is given."""
    get = MagicMock(side_effect=AssertionError("an import made a request"))
    monkeypatch.setattr(fetch.requests, "get", get)
    return get


@pytest.fixture
def pages(monkeypatch, session, tmp_path, network):
    """The parser's input for each file's bytes; returns the dict to add to."""
    served = {GOLD_PDF: _pages()}

    @contextmanager
    def same_session():
        yield session
        session.flush()

    monkeypatch.setattr(fetch, "SBC_RAW", tmp_path / "raw")
    monkeypatch.setattr(ingest, "SBC_ARCHIVE", tmp_path / "archive")
    monkeypatch.setattr(ingest, "SBC_REJECTED", tmp_path / "rejected")
    monkeypatch.setattr(ingest, "get_session", same_session)
    monkeypatch.setattr(import_pdf, "get_session", same_session)
    monkeypatch.setattr(ingest, "read_parsed", lambda path: (served[path.read_bytes()],
                                                             parse_sbc(served[path.read_bytes()])))
    return served


@pytest.fixture
def links(session, sbc_hosts):
    """California plans linked to one manual-only, one crawlable and one disabled host."""
    issuer = Issuer(hios_issuer_id="11111", plan_year=YEAR, name="Example Care", state="CA")
    session.add(issuer)
    session.flush()
    urls = {
        "manual": f"{sbc_hosts['manual']}gold.pdf",
        "query": f"{sbc_hosts['manual']}download?fileName=Silver_70_SBC.pdf",
        "crawl": f"{sbc_hosts['crawl']}bronze.pdf",
        "off": f"{sbc_hosts['off']}platinum.pdf",
    }
    for number, url in enumerate(urls.values(), 1):
        session.add(Plan(issuer_id=issuer.id, hios_plan_id=f"11111CA001000{number}", plan_year=YEAR,
                         marketing_name="Gold 80 HMO", metal_level="Gold", plan_type="HMO", state="CA",
                         benefits_url=url, hsa_eligible=False, has_national_network=False,
                         catalog_source=CATALOG_SOURCE))
    session.flush()
    return urls


def _download(folder: Path, name="gold.pdf", body=GOLD_PDF) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(body)
    return folder / name


def _document(session, url):
    return session.scalar(select(SbcDocument).where(SbcDocument.url == url, SbcDocument.plan_year == YEAR))


def _pdfs(tmp_path):
    return sorted(path.read_bytes() for path in (tmp_path / "raw").glob("**/*.pdf")) + sorted(
        path.read_bytes() for path in (tmp_path / "archive").glob("**/*.pdf"))


def test_a_downloaded_sbc_is_read_as_manual_with_no_request(pages, links, session, tmp_path, network):
    downloaded = _download(tmp_path / "downloads")

    assert import_file(downloaded, links["manual"], YEAR) == "ok"

    document = _document(session, links["manual"])
    assert (document.status, document.acquisition, document.title) == ("ok", "manual", "Example Gold")
    assert session.scalars(select(SbcChunk.section).where(SbcChunk.document_id == document.id)).all()
    assert fetch.cache_path(links["manual"], YEAR).read_bytes() == GOLD_PDF
    assert downloaded.read_bytes() == GOLD_PDF          # the person's own file is left where it was
    network.assert_not_called()


def test_a_corrected_download_archives_the_file_it_replaces(pages, links, session, tmp_path):
    import_file(_download(tmp_path / "downloads"), links["manual"], YEAR)
    pages[b"%PDF-1.7 gold v2"] = _pages(test_cost="$75")

    assert import_file(_download(tmp_path / "downloads", body=b"%PDF-1.7 gold v2"), links["manual"], YEAR) == "ok"

    assert _pdfs(tmp_path) == [b"%PDF-1.7 gold v2", GOLD_PDF]
    assert _document(session, links["manual"]).acquisition == "manual"


def test_importing_the_same_file_again_archives_nothing(pages, links, tmp_path):
    for _ in range(2):
        import_file(_download(tmp_path / "downloads"), links["manual"], YEAR)

    assert _pdfs(tmp_path) == [GOLD_PDF]


def test_a_download_for_another_year_is_refused_and_kept_aside(pages, links, session, tmp_path):
    pages[b"%PDF-1.7 last year"] = _pages(year=YEAR - 1)

    assert import_file(_download(tmp_path / "downloads", body=b"%PDF-1.7 last year"), links["manual"],
                       YEAR) == "wrong_year"

    assert _document(session, links["manual"]).acquisition == "manual"
    assert [p.read_bytes() for p in (tmp_path / "rejected").glob("**/*.pdf")] == [b"%PDF-1.7 last year"]


@pytest.mark.parametrize(("link", "body", "message"), [
    ("https://manual.example.com/sbc/nobody-links-this.pdf", GOLD_PDF, "no 1999 plan links to"),
    ("off", GOLD_PDF, "has no enabled sbc_host entry"),
    ("manual", b"<html>Sign in</html>", "is not a PDF"),
])
def test_a_file_that_cannot_be_imported_writes_nothing(pages, links, session, tmp_path, link, body, message):
    url = links.get(link, link)

    with pytest.raises(SbcImportError, match=message):
        import_file(_download(tmp_path / "downloads", body=body), url, YEAR)

    assert _document(session, url) is None
    assert not (tmp_path / "raw").exists()


def test_a_file_past_the_size_cap_is_refused(pages, links, session, tmp_path, monkeypatch):
    monkeypatch.setattr(import_pdf, "MAX_BYTES", len(GOLD_PDF) - 1)

    with pytest.raises(SbcImportError, match="not a Summary of Benefits"):
        import_file(_download(tmp_path / "downloads"), links["manual"], YEAR)


def test_a_path_that_is_not_a_file_is_refused(pages, links, tmp_path):
    with pytest.raises(SbcImportError, match="is not a file"):
        import_file(tmp_path / "missing.pdf", links["manual"], YEAR)


def test_a_folder_is_matched_to_manual_links_by_file_name(pages, links, session, tmp_path):
    """By the link's last path segment, or a query value naming the PDF (Blue Shield's ?fileName=)."""
    folder = tmp_path / "downloads"
    pages[b"%PDF-1.7 silver"] = _pages(test_cost="$90")
    _download(folder)
    _download(folder, "Silver_70_SBC.pdf", b"%PDF-1.7 silver")
    _download(folder, "bronze.pdf")                              # a crawlable link: never imported by hand
    _download(folder, "unrelated.pdf")
    (folder / "notes.txt").write_text("not a PDF")

    outcomes = import_folder(folder, YEAR)

    assert outcomes == {
        "Silver_70_SBC.pdf": "ok",
        "bronze.pdf": "not imported: no manual-only link ends in this file name",
        "gold.pdf": "ok",
        "unrelated.pdf": "not imported: no manual-only link ends in this file name",
    }
    assert _document(session, links["query"]).acquisition == "manual"
    assert _document(session, links["crawl"]) is None


def test_a_file_name_two_links_share_must_be_imported_with_its_url(pages, links, session, tmp_path, sbc_hosts):
    other = Plan(issuer_id=session.scalar(select(Issuer.id).where(Issuer.hios_issuer_id == "11111")),
                 hios_plan_id="11111CA0010009", plan_year=YEAR, marketing_name="Gold 80 HMO", metal_level="Gold",
                 plan_type="HMO", state="CA", benefits_url=f"{sbc_hosts['manual']}north/gold.pdf",
                 hsa_eligible=False, has_national_network=False, catalog_source=CATALOG_SOURCE)
    session.add(other)
    session.flush()

    outcomes = import_folder(_download(tmp_path / "downloads").parent, YEAR)

    assert outcomes == {"gold.pdf": "not imported: 2 links end in this file name; use FILE= and URL="}


def test_the_command_takes_one_file_with_its_url_or_a_folder():
    parsed = import_pdf.parse_args(["--year", "2026", "--file", "~/Downloads/x.pdf", "--url", "https://a.example/x.pdf"])
    assert parsed.file == Path.home() / "Downloads" / "x.pdf"      # make passes the path quoted, so ~ is expanded here
    assert import_pdf.parse_args(["--year", "2026", "--dir", "~/sbc"]).dir == Path.home() / "sbc"

    for args in (["--file", "x.pdf"], ["--dir", "d", "--url", "https://a.example/x.pdf"],
                 ["--file", "x.pdf", "--dir", "d"], []):
        with pytest.raises(SystemExit):
            import_pdf.parse_args(["--year", "2026", *args])


def test_the_command_reports_a_refusal_without_a_traceback(pages, links, tmp_path):
    with pytest.raises(SystemExit, match="Not imported: .* is not a PDF"):
        import_pdf.main(["--year", str(YEAR), "--file", str(_download(tmp_path / "d", body=b"<html>")),
                         "--url", links["manual"]])


def test_the_command_prints_each_files_outcome(pages, links, tmp_path, capsys):
    import_pdf.main(["--year", str(YEAR), "--dir", str(_download(tmp_path / "d").parent)])

    assert capsys.readouterr().out == "gold.pdf: ok\n"


def test_the_command_says_when_a_folder_has_no_pdfs(pages, links, tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(SystemExit, match="No PDFs in"):
        import_pdf.main(["--year", str(YEAR), "--dir", str(tmp_path / "empty")])


def test_a_matched_file_that_fails_a_check_is_reported_and_the_rest_imported(pages, links, session, tmp_path):
    folder = tmp_path / "downloads"
    _download(folder)
    _download(folder, "Silver_70_SBC.pdf", b"<html>Your session has expired</html>")

    outcomes = import_folder(folder, YEAR)

    assert outcomes["gold.pdf"] == "ok"
    assert outcomes["Silver_70_SBC.pdf"] == "not imported: Silver_70_SBC.pdf is not a PDF"
    assert _document(session, links["query"]) is None


def test_the_command_imports_one_file_and_prints_its_status(pages, links, tmp_path, capsys):
    import_pdf.main(["--year", str(YEAR), "--file", str(_download(tmp_path / "d")), "--url", links["manual"]])

    assert capsys.readouterr().out == "gold.pdf: ok\n"


def test_the_command_refuses_a_folder_that_is_not_one(tmp_path):
    with pytest.raises(SystemExit, match="is not a folder"):
        import_pdf.main(["--year", str(YEAR), "--dir", str(tmp_path / "nowhere")])
