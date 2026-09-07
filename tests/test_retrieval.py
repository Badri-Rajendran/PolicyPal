from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.policypal.config import settings
from src.services.retrieval import search


class _FakeSessionCtx:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return SimpleNamespace(execute=lambda stmt: SimpleNamespace(all=lambda: self._rows))

    def __exit__(self, *exc):
        return False


def test_search_returns_empty_list_for_blank_query():
    assert search("   ") == []


def test_search_rejects_top_k_below_minimum():
    with pytest.raises(ValueError):
        search("what is a deductible", top_k=3)


def test_search_returns_empty_when_no_candidates():
    with patch("src.services.retrieval._sparse_search", return_value=[]), \
         patch("src.services.retrieval._dense_search", return_value=[]):
        assert search("obscure query with no matches") == []


def test_search_filters_out_chunks_below_relevance_threshold():
    rows = [
        SimpleNamespace(chunk_id="c1", content="relevant content", source="Health_insurance"),
        SimpleNamespace(chunk_id="c2", content="irrelevant content", source="Health_insurance"),
    ]

    with patch("src.services.retrieval._sparse_search", return_value=["c1", "c2"]), \
         patch("src.services.retrieval._dense_search", return_value=[]), \
         patch("src.services.retrieval.get_session", return_value=_FakeSessionCtx(rows)), \
         patch("src.services.retrieval.rerank", return_value=[("c1", 5.0), ("c2", -5.0)]):
        results = search("what is a deductible")

    assert [r.chunk_id for r in results] == ["c1"]
    assert results[0].score >= settings.min_relevance_score
