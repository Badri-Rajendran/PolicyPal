from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.policypal.config import settings
from src.services.retrieval import _comparison_intents, _subqueries, search


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


# Multi-intent query decomposition

def test_subqueries_splits_a_compound_question():
    parts = _subqueries("What does in-network mean and why does it matter?")

    assert len(parts) == 2
    assert "What does in-network mean" in parts[0]
    assert "why does it matter" in parts[1]


def test_subqueries_splits_on_or_as_well_as_and():
    assert len(_subqueries("Should I buy term life cover or should I buy whole life?")) == 2


def test_subqueries_ignores_a_single_intent_question():
    """A plain question must not be decomposed — the fallback would be noise."""
    assert _subqueries("What is a deductible?") == []
    assert _subqueries("Do I need umbrella insurance?") == []


def test_subqueries_ignores_conjunctions_inside_one_intent():
    """"cost and coverage" is one idea; splitting it yields useless fragments."""
    assert _subqueries("Explain cost and coverage") == []


def test_subqueries_strips_trailing_punctuation():
    parts = _subqueries("What does in-network mean and why does it matter?")

    assert not any(part.endswith(("?", ",", ";")) for part in parts)


def _search_with(rerank_side_effect, query, rows):
    with patch("src.services.retrieval._sparse_search", return_value=[r.chunk_id for r in rows]), \
         patch("src.services.retrieval._dense_search", return_value=[]), \
         patch("src.services.retrieval.get_session", return_value=_FakeSessionCtx(rows)), \
         patch("src.services.retrieval.rerank", side_effect=rerank_side_effect):
        return search(query)


def test_compound_query_falls_back_to_subqueries_when_nothing_clears_the_gate():
    """The measured bug: 'X and why does it matter?' scored 0.49 as a whole,
    0.99 for its first half, so a real answer was dropped entirely."""
    rows = [SimpleNamespace(chunk_id="c1", content="In-network means contracted.",
                            source="hcg_glossary_Network.md")]

    def fake_rerank(query, pairs, k):
        # Whole query scores below the gate; the first subquery scores above it.
        score = -1.0 if "why does it matter" in query else 5.0
        return [(cid, score) for cid, _ in pairs]

    results = _search_with(fake_rerank, "What does in-network mean and why does it matter?", rows)

    assert [r.chunk_id for r in results] == ["c1"]


def test_subquery_fallback_does_not_run_when_the_whole_query_already_matched():
    """Best-of scoring can only raise scores, so it must never widen a query
    that already worked — that would weaken the relevance gate."""
    rows = [SimpleNamespace(chunk_id="c1", content="content", source="s.md")]
    calls = []

    def fake_rerank(query, pairs, k):
        calls.append(query)
        return [(cid, 5.0) for cid, _ in pairs]

    _search_with(fake_rerank, "What does in-network mean and why does it matter?", rows)

    assert calls == ["What does in-network mean and why does it matter?"]


def test_single_intent_query_that_matches_nothing_stays_empty():
    """No decomposition possible, so the gate still returns nothing."""
    rows = [SimpleNamespace(chunk_id="c1", content="content", source="s.md")]

    results = _search_with(lambda q, p, k: [(cid, -5.0) for cid, _ in p],
                           "Do I need umbrella insurance?", rows)

    assert results == []


def test_subquery_fallback_keeps_each_chunks_best_score():
    rows = [
        SimpleNamespace(chunk_id="c1", content="a", source="a.md"),
        SimpleNamespace(chunk_id="c2", content="b", source="b.md"),
    ]

    def fake_rerank(query, pairs, k):
        if "why does it matter" in query and "mean" in query:
            return [(cid, -5.0) for cid, _ in pairs]      # whole query: all fail
        if "mean" in query:
            return [("c1", 5.0), ("c2", -5.0)]            # first half favours c1
        return [("c1", -5.0), ("c2", 4.0)]                # second half favours c2

    results = _search_with(fake_rerank, "What does in-network mean and why does it matter?", rows)

    assert {r.chunk_id for r in results} == {"c1", "c2"}
    # Ordered by best score across subqueries, not by subquery order.
    assert [r.chunk_id for r in results] == ["c1", "c2"]


# Comparison queries

def test_comparison_intents_splits_difference_between():
    assert _comparison_intents("What's the difference between a copay and coinsurance?") == [
        "a copay", "coinsurance"
    ]


def test_comparison_intents_handles_vs_and_versus():
    assert _comparison_intents("HMO vs PPO") == ["HMO", "PPO"]
    assert _comparison_intents("term life versus whole life") == ["term life", "whole life"]


def test_comparison_intents_handles_compared_to():
    assert _comparison_intents("How is an HSA compared to an FSA") == ["How is an HSA", "an FSA"]


def test_comparison_intents_ignores_non_comparisons():
    """A conjunction alone isn't a comparison — that path is the fallback's job."""
    assert _comparison_intents("What is a deductible?") == []
    assert _comparison_intents("What does in-network mean and why does it matter?") == []


def test_comparison_retrieval_keeps_both_sides_in_context():
    """The measured bug: scoring every chunk against the whole query let the
    coinsurance chunks take every slot, so the copay definition never reached
    the model and it fabricated the comparison."""
    rows = [
        SimpleNamespace(chunk_id="copay", content="A copayment is a fixed amount.",
                        source="hcg_glossary_Copayment.md"),
        SimpleNamespace(chunk_id="coins", content="Coinsurance is a percentage.",
                        source="hcg_glossary_Coinsurance.md"),
    ]

    def fake_rerank(query, pairs, k):
        q = query.lower()
        if "copay" in q and "coinsurance" not in q:
            return [("copay", 5.0), ("coins", -5.0)][:k]
        if "coinsurance" in q and "copay" not in q:
            return [("coins", 5.0), ("copay", -5.0)][:k]
        # The whole query: coinsurance dominates, copay is gated out.
        return [("coins", 5.0), ("copay", -5.0)][:k]

    results = _search_with(fake_rerank, "What's the difference between a copay and coinsurance?", rows)

    assert {r.chunk_id for r in results} == {"copay", "coins"}


def test_comparison_retrieval_does_not_lose_whole_query_hits():
    rows = [
        SimpleNamespace(chunk_id="both", content="Copay and coinsurance both cost-share.",
                        source="hcg_article_Cost_sharing.md"),
        SimpleNamespace(chunk_id="copay", content="A copayment is fixed.",
                        source="hcg_glossary_Copayment.md"),
    ]

    def fake_rerank(query, pairs, k):
        if "copay" in query.lower() and "coinsurance" not in query.lower():
            return [("copay", 5.0), ("both", -5.0)][:k]
        return [("both", 5.0), ("copay", -5.0)][:k]

    results = _search_with(fake_rerank, "difference between a copay and coinsurance", rows)

    assert "both" in {r.chunk_id for r in results}


def test_comparison_results_stay_ordered_by_relevance():
    rows = [
        SimpleNamespace(chunk_id="a", content="A", source="a.md"),
        SimpleNamespace(chunk_id="b", content="B", source="b.md"),
    ]

    def fake_rerank(query, pairs, k):
        return ([("a", 5.0), ("b", 1.0)] if "term life" in query.lower()
                else [("b", 3.0), ("a", 0.5)])[:k]

    results = _search_with(fake_rerank, "difference between term life and whole life", rows)

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
