"""Storing SBCs: per document, incremental, and apart from the corpus (ADR 0013).

Real Postgres through the rolled-back `session` fixture. Fetching and PDF
reading are replaced; the parser is the real one, fed synthetic pages.
"""
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import func, insert, select

from src.ingestion import embed
from src.ingestion.sbc import ingest
from src.ingestion.sbc.extract import PdfPage, SbcParse, Section, TableRow
from src.ingestion.sbc.fetch import FetchResult
from src.models.chunk import Chunk
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings

YEAR = 1999
GOLD = "https://sbc.example.com/gold.pdf"
SILVER = "https://sbc.example.com/silver.pdf"


def _pages(year=YEAR, test_cost="$60"):
    header = f"Coverage Period: 01/01/{year}-12/31/{year}\n: Example Gold | Coverage for: Individual"
    rows = (TableRow("Common Medical Event", ""), TableRow("If you have a test", f"Imaging {test_cost} copay"))
    return [PdfPage(text=header, rows=rows)]


@pytest.fixture
def sbc(monkeypatch, session, tmp_path):
    """Serves each URL's pages from memory; returns the dict to change what is served."""
    served = {GOLD: _pages(), SILVER: _pages(test_cost="$90")}

    @contextmanager
    def same_session():
        yield session
        session.flush()

    def fake_fetch(url, year):
        if served[url] is None:
            return FetchResult("blocked", detail="HTTP 403")
        path = tmp_path / f"{abs(hash(url))}.pdf"
        path.write_bytes(url.encode())
        return FetchResult("ok", path)

    monkeypatch.setattr(ingest, "get_session", same_session)
    monkeypatch.setattr(ingest, "fetch_pdf", fake_fetch)
    monkeypatch.setattr(ingest, "read_pdf", lambda path: served[path.read_bytes().decode()])
    return served


def _chunks(session, url):
    return session.scalars(
        select(SbcChunk.content).join(SbcDocument).where(SbcDocument.url == url, SbcDocument.plan_year == YEAR)
    ).all()


def _status(session, url):
    return session.scalar(select(SbcDocument.status).where(SbcDocument.url == url, SbcDocument.plan_year == YEAR))


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


def test_an_sbc_for_another_year_is_refused_and_its_download_discarded(sbc, session, tmp_path):
    sbc[GOLD] = _pages(year=YEAR - 1)

    assert ingest.ingest_document(GOLD, YEAR) == "wrong_year"

    assert _chunks(session, GOLD) == []
    detail = session.scalar(select(SbcDocument.detail).where(SbcDocument.url == GOLD))
    assert detail == f"coverage period starts in {YEAR - 1}"
    assert list(tmp_path.glob("*.pdf")) == []


def test_documents_are_grouped_by_url_within_the_states_and_year(session):
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Example Health", state="NH")
    session.add(issuer)
    session.flush()
    for plan_id, state, url, year in [
        ("99999NH0010001", "NH", GOLD, YEAR),
        ("99999NH0010002", "NH", GOLD, YEAR),
        ("99999NH0010003", "NH", SILVER, YEAR - 1),
        ("99999NH0010004", "DE", SILVER, YEAR),
        ("99999NH0010005", "NH", None, YEAR),
    ]:
        session.add(Plan(issuer_id=issuer.id, hios_plan_id=plan_id, plan_year=year, marketing_name=plan_id,
                         metal_level="Gold", plan_type="HMO", state=state, benefits_url=url,
                         hsa_eligible=False, has_national_network=False))
    session.flush()

    documents = ingest.documents_for(session, ["NH"], YEAR)

    assert list(documents) == [GOLD]
    assert [plan.hios_plan_id for plan in documents[GOLD]] == ["99999NH0010001", "99999NH0010002"]


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
