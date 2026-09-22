"""Storing SBCs: per document, incremental, and apart from the corpus (ADR 0013).

Real Postgres through the rolled-back `session` fixture. Fetching and PDF
reading are replaced; the parser is the real one, fed synthetic pages.
"""
import json
import os
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, insert, select

from src.ingestion import embed
from src.ingestion.sbc import ingest
from src.ingestion.sbc.extract import (
    EVENT_HEADINGS,
    QUESTION_HEADINGS,
    PdfPage,
    SbcParse,
    Section,
    TableRow,
    parse_sbc,
)
from src.ingestion.sbc.fetch import FetchResult
from src.models.chunk import Chunk
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings

YEAR = 1999
GOLD = "https://sbc.example.com/gold.pdf"
SILVER = "https://sbc.example.com/silver.pdf"


def _template_rows(test_cost):
    """The federal template's questions and chart groups, so a document is whole."""
    return [("Important Questions", "Answers | Why This Matters:")] + [
        (heading, "No.") for heading in QUESTION_HEADINGS] + [("Common Medical Event", "")] + [
        (heading, f"Imaging {test_cost} copay" if heading == "If you have a test" else "No charge")
        for heading in EVENT_HEADINGS]


def _pages(year=YEAR, test_cost="$60"):
    header = f"Coverage Period: 01/01/{year}-12/31/{year}\n: Example Gold | Coverage for: Individual"
    rows = tuple(TableRow(label, body) for label, body in _template_rows(test_cost))
    return [PdfPage(text=header, rows=rows)]


@pytest.fixture
def sbc(monkeypatch, session, tmp_path):
    """Serves each URL's pages from memory; returns the dict to change what is served."""
    served = {GOLD: _pages(), SILVER: _pages(test_cost="$90")}

    @contextmanager
    def same_session():
        yield session
        session.flush()

    def cached(url, year):
        return tmp_path / f"{abs(hash(url))}.pdf"

    def fake_fetch(url, year):
        if served[url] is None:
            return FetchResult("blocked", detail="HTTP 403")
        path = cached(url, year)
        if not path.exists():   # a kept PDF is served from disk, as fetch_pdf does
            path.write_bytes(url.encode())
        return FetchResult("ok", path)

    monkeypatch.setattr(ingest, "cache_path", cached)
    monkeypatch.setattr(ingest, "SBC_REJECTED", tmp_path / "rejected")
    monkeypatch.setattr(ingest, "get_session", same_session)
    monkeypatch.setattr(ingest, "fetch_pdf", fake_fetch)
    def read_parsed(path):
        pages = served[path.read_bytes().decode()]
        return pages, parse_sbc(pages)

    monkeypatch.setattr(ingest, "read_parsed", read_parsed)
    return served


@pytest.fixture
def fetches(sbc, monkeypatch):
    """The URLs fetched, in order."""
    calls = []
    fetch = ingest.fetch_pdf
    monkeypatch.setattr(ingest, "fetch_pdf", lambda url, year: calls.append(url) or fetch(url, year))
    return calls


@pytest.fixture
def catalog(monkeypatch):
    plan = ingest.PlanRef("99999NH0010001", "Example Gold", "Example Health")
    monkeypatch.setattr(ingest, "documents_for", lambda session, states, year, issuer_ids: {GOLD: [plan], SILVER: [plan]})


def _chunks(session, url):
    """The chart row the tests vary; the rest of the template is the same in every fixture."""
    return [content for content in session.scalars(
        select(SbcChunk.content).join(SbcDocument).where(SbcDocument.url == url, SbcDocument.plan_year == YEAR))
        if content.startswith("If you have a test")]


def _row(session, url):
    """The stored row as `execute` reads it: status, parser version and hash."""
    return session.execute(
        select(SbcDocument.url, SbcDocument.status, SbcDocument.parser_version, SbcDocument.sha256)
        .where(SbcDocument.url == url)).first()


def _status(session, url):
    return session.scalar(select(SbcDocument.status).where(SbcDocument.url == url, SbcDocument.plan_year == YEAR))


def _version(session, url):
    return session.scalar(select(SbcDocument.parser_version).where(SbcDocument.url == url))


def test_a_document_is_stored_with_one_chunk_per_section(sbc, session):
    assert ingest.ingest_document(GOLD, YEAR) == "ok"

    assert _chunks(session, GOLD) == ["If you have a test\nImaging $60 copay"]
    document = session.scalar(select(SbcDocument).where(SbcDocument.url == GOLD))
    assert (document.title, document.pages, len(document.sha256)) == ("Example Gold", 1, 64)


def test_reingesting_replaces_that_documents_chunks_and_no_other(sbc, session):
    ingest.ingest_document(GOLD, YEAR)
    ingest.ingest_document(SILVER, YEAR)

    sbc[GOLD] = _pages(test_cost="$75")
    ingest.ingest_document(GOLD, YEAR)

    assert _chunks(session, GOLD) == ["If you have a test\nImaging $75 copay"]
    assert _chunks(session, SILVER) == ["If you have a test\nImaging $90 copay"]


def test_a_document_that_now_fails_loses_its_chunks(sbc, session):
    """An answer must never quote an SBC that is no longer the plan's."""
    ingest.ingest_document(GOLD, YEAR)

    sbc[GOLD] = None
    assert ingest.ingest_document(GOLD, YEAR) == "blocked"

    assert _status(session, GOLD) == "blocked"
    assert _chunks(session, GOLD) == []
    assert _version(session, GOLD) is None


def test_an_sbc_for_another_year_is_refused_and_moved_aside_not_deleted(sbc, session, tmp_path):
    """Out of the cache, so a corrected file at the same URL is downloaded; kept, never deleted (ADR 0016)."""
    sbc[GOLD] = _pages(year=YEAR - 1)

    assert ingest.ingest_document(GOLD, YEAR) == "wrong_year"

    assert _chunks(session, GOLD) == []
    detail = session.scalar(select(SbcDocument.detail).where(SbcDocument.url == GOLD))
    assert detail == f"coverage period starts in {YEAR - 1}"
    assert list(tmp_path.glob("*.pdf")) == []
    [rejected] = (tmp_path / "rejected" / str(YEAR)).glob("*.pdf")
    assert rejected.read_bytes() == GOLD.encode()


def test_a_file_the_parser_turns_down_keeps_its_hash_and_the_parser_that_judged_it(sbc, session):
    """ADR 0018: which file was refused, and by which parser, so a parser change can judge it again."""
    sbc[GOLD] = []
    sbc[SILVER] = _pages(year=YEAR - 1)

    ingest.ingest_document(GOLD, YEAR)
    ingest.ingest_document(SILVER, YEAR)

    for url in (GOLD, SILVER):
        document = session.scalar(select(SbcDocument).where(SbcDocument.url == url))
        assert (len(document.sha256), document.parser_version) == (64, ingest.PARSER_VERSION)


def test_fetched_at_is_when_the_pdf_was_downloaded_not_when_it_was_parsed(sbc, session, tmp_path):
    ingest.ingest_document(GOLD, YEAR)
    downloaded = datetime(2026, 1, 15, 9, 30, tzinfo=UTC)
    os.utime(ingest.cache_path(GOLD, YEAR), (downloaded.timestamp(), downloaded.timestamp()))

    ingest.ingest_document(GOLD, YEAR)

    assert session.scalar(select(SbcDocument.fetched_at).where(SbcDocument.url == GOLD)) == downloaded


def test_documents_are_grouped_by_url_within_the_states_and_year(session):
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Example Health", state="NH")
    other = Issuer(hios_issuer_id="88888", plan_year=YEAR, name="Other Health", state="NH")
    session.add_all([issuer, other])
    session.flush()
    for owner, plan_id, state, url, year in [
        (issuer, "99999NH0010001", "NH", GOLD, YEAR),
        (issuer, "99999NH0010002", "NH", GOLD, YEAR),
        (issuer, "99999NH0010003", "NH", SILVER, YEAR - 1),
        (issuer, "99999NH0010004", "DE", SILVER, YEAR),
        (issuer, "99999NH0010005", "NH", None, YEAR),
        (other, "88888NH0010001", "NH", SILVER, YEAR),
    ]:
        session.add(Plan(issuer_id=owner.id, hios_plan_id=plan_id, plan_year=year, marketing_name=plan_id,
                         metal_level="Gold", plan_type="HMO", state=state, benefits_url=url,
                         hsa_eligible=False, has_national_network=False))
    session.flush()

    documents = ingest.documents_for(session, ["NH"], YEAR)

    assert list(documents) == [GOLD, SILVER]
    assert [plan.hios_plan_id for plan in documents[GOLD]] == ["99999NH0010001", "99999NH0010002"]
    assert list(ingest.documents_for(session, ["NH"], YEAR, frozenset({"99999"}))) == [GOLD]


def test_a_document_stored_by_this_parser_is_not_read_again(sbc, fetches, catalog, session):
    ingest.execute(["NH"], YEAR)
    assert fetches == [GOLD, SILVER]

    fetches.clear()
    assert ingest.execute(["NH"], YEAR) == Counter()
    assert fetches == []


def test_an_empty_catalog_says_to_ingest_plans_first(sbc, monkeypatch):
    monkeypatch.setattr(ingest, "documents_for", lambda session, states, year, issuer_ids: {})

    with pytest.raises(SystemExit, match="make ingest-plans STATES=NH"):
        ingest.execute(["NH"], YEAR)


def test_a_parser_change_reads_stored_documents_again(sbc, fetches, catalog, session, monkeypatch):
    ingest.execute(["NH"], YEAR)

    monkeypatch.setattr(ingest, "PARSER_VERSION", ingest.PARSER_VERSION + 1)
    sbc[GOLD] = _pages(test_cost="$75")
    fetches.clear()
    ingest.execute(["NH"], YEAR)

    assert fetches == [GOLD, SILVER]
    assert _chunks(session, GOLD) == ["If you have a test\nImaging $75 copay"]
    assert _version(session, GOLD) == ingest.PARSER_VERSION


def test_every_downloaded_pdf_is_kept_parsed_or_not(sbc, fetches, catalog, session, tmp_path):
    sbc[SILVER] = []

    ingest.execute(["NH"], YEAR)
    ingest.execute(["NH"], YEAR)

    assert (_status(session, GOLD), _status(session, SILVER)) == ("ok", "unparseable")
    assert len(list(tmp_path.glob("*.pdf"))) == 2


def test_a_stored_document_whose_pdf_is_missing_is_downloaded_again(sbc, fetches, catalog, session, tmp_path):
    ingest.execute(["NH"], YEAR)
    ingest.cache_path(GOLD, YEAR).unlink()

    fetches.clear()
    ingest.execute(["NH"], YEAR)

    assert fetches == [GOLD]
    assert ingest.cache_path(GOLD, YEAR).exists()


def test_a_long_section_is_split_and_every_piece_keeps_its_heading():
    long_text = "\n".join(f"Service {i}: $10 copay after deductible" for i in range(120))
    parse = SbcParse("Plan", YEAR, (Section("If you have a test", long_text),))

    chunks = ingest.build_chunks(GOLD, YEAR, parse)

    assert len(chunks) > 1
    assert all(c["content"].startswith("If you have a test\n") for c in chunks)
    assert len({c["chunk_id"] for c in chunks}) == len(chunks)


def test_rebuilding_the_corpus_leaves_sbc_chunks_alone(sbc, session, monkeypatch, tmp_path):
    ingest.ingest_document(GOLD, YEAR)
    corpus = tmp_path / "all_chunks.jsonl"
    corpus.write_text(json.dumps({
        "text": "A deductible is...", "contextualized_text": "Deductible: A deductible is...",
        "metadata": {"source_file": "hcg_glossary_deductible.md", "chunk_id": "test_deductible_c00"},
    }))

    @contextmanager
    def same_session():
        yield session
        session.flush()

    monkeypatch.setattr(embed, "get_session", same_session)
    monkeypatch.setattr(embed, "embed_texts", lambda texts: [[0.0] * settings.embedding_dim for _ in texts])
    session.execute(insert(Chunk), [{"content": "old", "source": "old.md", "chunk_id": "old_c00",
                                     "embedding": [0.0] * settings.embedding_dim}])

    embed.execute(corpus, rebuild=True)

    assert session.scalars(select(Chunk.chunk_id).where(Chunk.chunk_id.in_(["old_c00", "test_deductible_c00"]))).all() == ["test_deductible_c00"]
    assert _chunks(session, GOLD) == ["If you have a test\nImaging $60 copay"]
    assert session.scalar(select(func.count()).select_from(SbcChunk)) >= 1


@pytest.mark.parametrize(("args", "expected"), [
    ([], None),
    (["--top-issuers"], ingest.TOP_ISSUER_IDS),
    (["--issuers", "40788, 66252"], frozenset({"40788", "66252"})),
])
def test_a_run_is_narrowed_to_the_issuers_asked_for(args, expected):
    assert ingest.parse_args(["--states", "TX", *args]).issuer_ids == expected


@pytest.mark.parametrize("args", [
    ["--issuers", "4078"],
    ["--issuers", ","],
    ["--issuers", "40788", "--top-issuers"],
])
def test_issuers_must_be_hios_ids_and_not_mixed_with_the_top_list(args):
    with pytest.raises(SystemExit):
        ingest.parse_args(["--states", "TX", *args])


def test_a_parser_that_now_reads_the_year_judges_the_file_it_turned_down_again(sbc, session, tmp_path):
    """A later parser reads the kept file from disk, not from the issuer again (ADR 0018)."""
    sbc[GOLD] = _pages(year=YEAR - 1)
    assert ingest.ingest_document(GOLD, YEAR) == "wrong_year"
    row = _row(session, GOLD)

    sbc[GOLD] = _pages()                                      # the same file, read by a better parser

    assert ingest.ingest_document(GOLD, YEAR, row) == "ok"

    assert _chunks(session, GOLD) == ["If you have a test\nImaging $60 copay"]
    assert list((tmp_path / "rejected" / str(YEAR)).glob("*.pdf")) == []
    assert ingest.cache_path(GOLD, YEAR).read_bytes() == GOLD.encode()


def test_a_run_reads_a_wrong_year_document_again_only_when_the_parser_changed(sbc, session):
    def judged_by(version):
        return SimpleNamespace(status="wrong_year", parser_version=version, sha256="a" * 64)

    assert ingest._needs_reading(GOLD, judged_by(ingest.PARSER_VERSION - 1), YEAR, refresh=False) is True
    assert ingest._needs_reading(GOLD, judged_by(ingest.PARSER_VERSION), YEAR, refresh=False) is False


def test_a_document_without_the_chart_is_partial_and_keeps_the_text_it_has(sbc, session):
    """University of Utah's chart is no table pdfplumber finds; what was read is still the plan's (ADR 0017)."""
    header = f"Coverage Period: 01/01/{YEAR}-12/31/{YEAR}\n: Example Gold | Coverage for: Individual"
    questions = [("Important Questions", "Answers")] + [(heading, "No.") for heading in QUESTION_HEADINGS]
    sbc[GOLD] = [PdfPage(text=header, rows=tuple(TableRow(*row) for row in questions))]

    assert ingest.ingest_document(GOLD, YEAR) == "partial"

    assert _status(session, GOLD) == "partial"
    detail = session.scalar(select(SbcDocument.detail).where(SbcDocument.url == GOLD))
    assert detail == "missing the whole costs chart"
    stored = session.scalars(select(SbcChunk.content).join(SbcDocument).where(SbcDocument.url == GOLD)).all()
    assert any(content.startswith("What is the overall deductible?") for content in stored)


def test_a_document_missing_some_of_its_questions_says_how_many(sbc, session):
    pages = _pages()
    kept = [row for row in pages[0].rows if row.label not in QUESTION_HEADINGS[:3]]
    sbc[GOLD] = [PdfPage(text=pages[0].text, rows=tuple(kept))]

    assert ingest.ingest_document(GOLD, YEAR) == "partial"

    detail = session.scalar(select(SbcDocument.detail).where(SbcDocument.url == GOLD))
    assert detail == "missing 3 of the 7 questions"


def test_a_partly_read_document_is_neither_a_failure_nor_a_skipped_one(sbc, fetches, catalog, session, capsys):
    """It was read. Listing it as a failure would send the operator to refresh what did not fail."""
    pages = _pages()
    kept = [row for row in pages[0].rows if row.label not in QUESTION_HEADINGS[:3]]
    sbc[GOLD] = [PdfPage(text=pages[0].text, rows=tuple(kept))]

    ingest.execute(["NH"], YEAR)

    assert _status(session, GOLD) == "partial"
    assert "Plans without a usable SBC" not in capsys.readouterr().out

    fetches.clear()
    assert ingest.execute(["NH"], YEAR) == Counter()
    assert "recorded failures skipped" not in capsys.readouterr().out
    assert fetches == []
