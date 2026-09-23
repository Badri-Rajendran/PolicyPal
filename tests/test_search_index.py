"""The BM25 index, stored in the database rather than on local disk (ADR 0021).

Real Postgres through the rolled-back `session` fixture. The only pickle
loaded here is the one these tests just built through the code under test.
"""
import pickle
from contextlib import contextmanager

import pytest
from sqlalchemy import select

from src.core.exceptions import MissingSearchIndexError
from src.ingestion import build_index, chunking
from src.models.chunk import Chunk
from src.models.search_index import BM25_INDEX, SearchIndex
from src.services import retrieval

# BM25Okapi's idf is log((N - df + 0.5) / (df + 0.5)), which is exactly 0 for a
# term in one document of two — and `_sparse_search` keeps only scores above 0.
# Three documents is the smallest corpus where a hit actually scores.
_CORPUS = ["a deductible is what you pay first", "a copay is a flat fee", "a premium is monthly"]
_IDS = ["c1", "c2", "c3"]


@pytest.fixture
def stores(monkeypatch, session):
    """Point everything that opens its own session at the rolled-back one."""
    @contextmanager
    def same_session():
        yield session
        session.flush()

    for module in (chunking, build_index, retrieval):
        monkeypatch.setattr(module, "get_session", same_session)
    # The real database has a built index and a loaded corpus; neither belongs
    # in these assertions. Removed inside the transaction that is rolled back.
    session.query(SearchIndex).delete()
    session.query(Chunk).delete()
    session.flush()
    retrieval._bm25_index.cache_clear()
    yield
    retrieval._bm25_index.cache_clear()


def _stored(session):
    return session.scalar(select(SearchIndex).where(SearchIndex.name == BM25_INDEX))


def test_the_index_is_stored_with_the_chunk_count(stores, session):
    chunking.build_and_store_index(["a deductible is what you pay first"], ["c1"])

    row = _stored(session)
    assert (row.name, row.chunks) == (BM25_INDEX, 1)
    assert row.built_at is not None


def test_the_payload_carries_the_ids_but_not_the_texts(stores, session):
    """Retrieval reads `bm25` and `chunk_ids` only; the text is a column away."""
    chunking.build_and_store_index(_CORPUS, _IDS)

    index = pickle.loads(_stored(session).payload)

    assert set(index) == {"bm25", "chunk_ids"}
    assert index["chunk_ids"] == _IDS
    assert index["bm25"].corpus_size == 3


def test_rebuilding_replaces_the_one_row(stores, session):
    chunking.build_and_store_index(["first"], ["c1"])
    chunking.build_and_store_index(_CORPUS, _IDS)

    assert session.scalars(select(SearchIndex.name)).all() == [BM25_INDEX]
    assert _stored(session).chunks == 3


def test_retrieval_reads_the_stored_index(stores, session):
    chunking.build_and_store_index(_CORPUS, _IDS)

    assert retrieval._sparse_search("deductible", top_k=5) == ["c1"]


def test_retrieval_says_what_to_run_when_no_index_is_stored(stores):
    with pytest.raises(MissingSearchIndexError, match="make build-index"):
        retrieval._bm25_index()


def test_build_index_rebuilds_from_the_chunks_already_stored(stores, session):
    """A database seeded from a dump has the chunks; the index is derived from them."""
    session.add_all([
        Chunk(content=content, source=f"{chunk_id}.md", chunk_id=chunk_id, embedding=[0.0] * 384)
        for content, chunk_id in zip(_CORPUS, _IDS, strict=True)
    ])
    session.flush()

    build_index.main()

    assert _stored(session).chunks == 3
    assert retrieval._sparse_search("copay", top_k=5) == ["c2"]


def test_build_index_says_what_to_run_when_there_are_no_chunks(stores):
    with pytest.raises(SystemExit, match="make ingest"):
        build_index.main()
