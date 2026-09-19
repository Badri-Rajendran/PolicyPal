"""Keeping stored SBCs current: `make refresh-sbc` (ADR 0019).

Real Postgres through the rolled-back `session` fixture. The issuer is a
dictionary of replies; the parser is the real one, fed synthetic pages.

Every PDF ever written is accounted for at the end of each test: ADR 0016
says none may be deleted, and a refresh is where one could be.
"""
from collections import Counter
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from src.ingestion.sbc import ingest
from src.ingestion.sbc.extract import PdfPage, TableRow
from src.ingestion.sbc.fetch import NOT_MODIFIED, FetchResult
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument

YEAR = 1999
GOLD = "https://sbc.example.com/gold.pdf"


def _pages(test_cost="$60"):
    header = f"Coverage Period: 01/01/{YEAR}-12/31/{YEAR}\n: Example Gold | Coverage for: Individual"
    rows = (TableRow("Common Medical Event", ""), TableRow("If you have a test", f"Imaging {test_cost} copay"))
    return [PdfPage(text=header, rows=rows)]


class Issuerer:
    """What the issuer's site returns, and what it has been asked."""

    def __init__(self):
        self.body = b"%PDF gold"
        self.pages = {self.body: _pages()}
        self.reply = None          # a FetchResult to give instead of the body
        self.asked = []

    def serve(self, body, pages):
        self.body, self.pages[body] = body, pages

    def revalidate(self, url, etag=None, last_modified=None):
        self.asked.append((url, etag, last_modified))
        return self.reply or FetchResult("ok", body=self.body, etag='"v2"')


@pytest.fixture
def issuer(monkeypatch, session, tmp_path):
    site = Issuerer()

    @contextmanager
    def same_session():
        yield session
        session.flush()

    def cached(url, year):
        return tmp_path / "raw" / f"{abs(hash(url))}.pdf"

    def fetch(url, year):
        path = cached(url, year)
        if path.exists():
            return FetchResult("ok", path)
        if site.reply and site.reply.status != NOT_MODIFIED:
            return site.reply
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(site.body)
        return FetchResult("ok", path)

    monkeypatch.setattr(ingest, "cache_path", cached)
    monkeypatch.setattr(ingest, "SBC_ARCHIVE", tmp_path / "archive")
    monkeypatch.setattr(ingest, "SBC_REJECTED", tmp_path / "rejected")
    monkeypatch.setattr(ingest, "get_session", same_session)
    monkeypatch.setattr(ingest, "fetch_pdf", fetch)
    monkeypatch.setattr(ingest, "revalidate", site.revalidate)
    monkeypatch.setattr(ingest, "read_pdf", lambda path: site.pages[path.read_bytes()])
    monkeypatch.setattr(ingest, "save", lambda body, target: target.write_bytes(body))
    return site


@pytest.fixture
def catalog(monkeypatch, session):
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Example Health", state="NH")
    session.add(issuer)
    session.flush()
    session.add(Plan(issuer_id=issuer.id, hios_plan_id="99999NH0010001", plan_year=YEAR, marketing_name="Gold",
                     metal_level="Gold", plan_type="HMO", state="NH", benefits_url=GOLD,
                     hsa_eligible=False, has_national_network=False))
    session.flush()


def _document(session):
    return session.scalar(select(SbcDocument).where(SbcDocument.url == GOLD))


def _chunks(session):
    return session.scalars(select(SbcChunk.content).join(SbcDocument).where(SbcDocument.url == GOLD)).all()


def _pdfs(tmp_path):
    return sorted(path.read_bytes() for path in tmp_path.glob("**/*.pdf"))


def _stored(session):
    return session.execute(
        select(SbcDocument.url, SbcDocument.status, SbcDocument.parser_version, SbcDocument.sha256,
               SbcDocument.etag, SbcDocument.last_modified).where(SbcDocument.url == GOLD)
    ).first()


def _refresh(session, tmp_path):
    return ingest.refresh_document(GOLD, YEAR, _stored(session))


def test_an_unchanged_document_is_left_alone_and_stamped_as_checked(issuer, session, catalog, tmp_path):
    ingest.ingest_document(GOLD, YEAR)
    before = _document(session)
    issuer.reply = FetchResult(NOT_MODIFIED)

    assert _refresh(session, tmp_path) == "unchanged"

    document = _document(session)
    assert (document.sha256, document.fetched_at) == (before.sha256, before.fetched_at)
    assert document.checked_at is not None
    assert _chunks(session) == ["If you have a test\nImaging $60 copay"]


def test_the_same_bytes_without_a_validator_change_nothing_but_the_check(issuer, session, catalog, tmp_path):
    """An issuer that sends no ETag is asked in full; identical bytes are not rewritten."""
    ingest.ingest_document(GOLD, YEAR)
    pdfs = _pdfs(tmp_path)

    assert _refresh(session, tmp_path) == "unchanged"

    assert _pdfs(tmp_path) == pdfs
    assert _document(session).etag == '"v2"'


def test_a_changed_pdf_is_archived_under_its_old_hash_and_the_new_one_parsed(issuer, session, catalog, tmp_path):
    ingest.ingest_document(GOLD, YEAR)
    old = _document(session).sha256
    issuer.serve(b"%PDF gold v2", _pages(test_cost="$75"))

    assert _refresh(session, tmp_path) == "changed:ok"

    assert _chunks(session) == ["If you have a test\nImaging $75 copay"]
    assert _document(session).sha256 != old
    [archived] = (tmp_path / "archive" / str(YEAR)).glob("*.pdf")
    assert archived.read_bytes() == b"%PDF gold"
    assert old[:12] in archived.name
    assert ingest.cache_path(GOLD, YEAR).read_bytes() == b"%PDF gold v2"


def test_a_document_the_issuer_replaced_with_another_years_is_moved_aside_not_deleted(issuer, session, catalog, tmp_path):
    ingest.ingest_document(GOLD, YEAR)
    pages = _pages()
    pages[0] = PdfPage(text=pages[0].text.replace(str(YEAR), str(YEAR + 1)), rows=pages[0].rows)
    issuer.serve(b"%PDF next year", pages)

    assert _refresh(session, tmp_path) == "changed:wrong_year"

    assert _chunks(session) == []
    assert _pdfs(tmp_path) == sorted([b"%PDF gold", b"%PDF next year"])


def test_a_transient_failure_keeps_the_stored_text(issuer, session, catalog, tmp_path):
    """A 5xx or a timeout says nothing about the document (ADR 0019)."""
    ingest.ingest_document(GOLD, YEAR)
    issuer.reply = FetchResult("http_error", detail="HTTP 503", transient=True)

    assert _refresh(session, tmp_path) == "unreachable"

    document = _document(session)
    assert (document.status, document.checked_at) == ("ok", None)
    assert _chunks(session) == ["If you have a test\nImaging $60 copay"]
    assert ingest.cache_path(GOLD, YEAR).exists()


@pytest.mark.parametrize(("reply", "status"), [
    (FetchResult("http_error", detail="HTTP 404"), "http_error"),
    (FetchResult("blocked", detail="robots.txt disallows it"), "blocked"),
    (FetchResult("not_pdf", detail="response is not a PDF"), "not_pdf"),
])
def test_a_document_that_is_gone_or_now_refused_loses_its_text_but_not_its_file(
        issuer, session, catalog, tmp_path, reply, status):
    ingest.ingest_document(GOLD, YEAR)
    issuer.reply = reply

    assert _refresh(session, tmp_path) == status

    assert (_document(session).status, _chunks(session)) == (status, [])
    assert _pdfs(tmp_path) == [b"%PDF gold"]
    assert not ingest.cache_path(GOLD, YEAR).exists()


def test_a_run_reads_what_is_new_and_leaves_recorded_failures_to_a_refresh(issuer, session, catalog, monkeypatch,
                                                                          tmp_path):
    monkeypatch.setattr(ingest, "documents_for",
                        lambda session, states, year, issuer_ids: {GOLD: [ingest.PlanRef("99999NH0010001", "Gold", "Example")]})
    issuer.reply = FetchResult("blocked", detail="robots.txt disallows it")
    assert ingest.execute(["NH"], YEAR) == Counter({"blocked": 1})

    asked = len(issuer.asked)
    assert ingest.execute(["NH"], YEAR) == Counter()          # the failure is not tried again
    assert ingest.execute(["NH"], YEAR, refresh=True) == Counter({"blocked": 1})
    assert len(issuer.asked) == asked                          # a failure is downloaded again, not revalidated


def test_a_refresh_asks_about_every_stored_document(issuer, session, catalog, monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "documents_for",
                        lambda session, states, year, issuer_ids: {GOLD: [ingest.PlanRef("99999NH0010001", "Gold", "Example")]})
    ingest.execute(["NH"], YEAR)
    issuer.reply = FetchResult(NOT_MODIFIED)

    assert ingest.execute(["NH"], YEAR, refresh=True) == Counter({"unchanged": 1})
    assert issuer.asked == [(GOLD, None, None)]


def test_every_pdf_ever_written_is_still_on_disk_after_any_run(issuer, session, catalog, tmp_path):
    """The rule ADR 0016 exists for: no refresh, however it turns out, deletes a document."""
    written = []
    ingest.ingest_document(GOLD, YEAR)
    written.append(b"%PDF gold")

    for body, cost in ((b"%PDF gold v2", "$75"), (b"%PDF gold v3", "$80")):
        issuer.serve(body, _pages(test_cost=cost))
        _refresh(session, tmp_path)
        written.append(body)

    issuer.reply = FetchResult("blocked", detail="robots.txt disallows it")
    _refresh(session, tmp_path)

    assert _pdfs(tmp_path) == sorted(written)


def test_refresh_is_a_flag_on_the_ingest_command():
    assert ingest.parse_args(["--states", "NH", "--refresh"]).refresh is True
    assert ingest.parse_args(["--states", "NH"]).refresh is False
