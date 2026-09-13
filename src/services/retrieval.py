import math
import pickle as pkl
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select

from src.core.db import get_session
from src.core.embedding import embed_query
from src.core.logging import get_logger
from src.core.reranker import rerank
from src.models.chunk import Chunk
from src.policypal.config import settings

logger = get_logger(__name__)

@dataclass
class RetrievedChunk:
    chunk_id: str
    content: str
    source: str
    score: float            # reranker relevance: sigmoid(cross-encoder logit), (0, 1)



@lru_cache
def _bm25_index() -> dict:
    index_path = Path(settings.bm25_index_path)

    if not index_path.exists():
        raise FileNotFoundError(f"BM25 index not found at {index_path}. Run the chunk stage first.")
    
    with index_path.open("rb") as file:
        # This file is only ever produced by our own ingestion pipeline
        # (src/ingestion/chunk.py), never from user input or an external
        # source, so there's no untrusted data to deserialize here.
        return pkl.load(file)  # nosec B301


def _sparse_search(query: str, top_k: int) -> list[str]:
    index = _bm25_index()
    bm25_index = index["bm25"]
    chunk_ids = index["chunk_ids"]

    scores = bm25_index.get_scores(query.lower().split())

    ranked = sorted(zip(chunk_ids, scores), key=lambda x: x[1], reverse=True)

    return [chunk_id for chunk_id, score in ranked[:top_k] if score > 0]


# A question joined by a conjunction carries more than one intent.
_CONJUNCTION_RE = re.compile(r"\s+(?:and|or)\s+|\s*[;?]\s+", re.IGNORECASE)

# Below this a fragment is a connective ("why does it matter"), not a question
# worth reranking on its own.
_MIN_SUBQUERY_WORDS = 3


def _subqueries(query: str) -> list[str]:
    """Split a multi-intent question into its parts, or return [] if it isn't one.

    A cross-encoder scores one (query, passage) pair, so it asks "does this
    passage answer the *whole* query". No single chunk answers both halves of
    "What does in-network mean and why does it matter?", and the score
    collapses far enough to fall below the relevance gate — measured at 0.99
    for the first half alone versus 0.49 for the pair. Scoring the parts
    separately lets a chunk that fully answers one intent be found.
    """
    parts = [part.strip(" ,;?!") for part in _CONJUNCTION_RE.split(query)]
    parts = [part for part in parts if len(part.split()) >= _MIN_SUBQUERY_WORDS]

    return parts if len(parts) >= 2 else []


def _best_scores_across(subqueries: list[str], pairs: list[tuple[str, str]],
                        top_k: int) -> list[tuple[str, float]]:
    """Rerank against each subquery, keeping each chunk's best score."""
    best: dict[str, float] = {}

    for subquery in subqueries:
        for chunk_id, raw_score in rerank(subquery, pairs, len(pairs)):
            score = float(raw_score)
            if chunk_id not in best or score > best[chunk_id]:
                best[chunk_id] = score

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


# "What's the difference between X and Y", "X vs Y", "X compared to Y".
_COMPARISON_CUE_RE = re.compile(
    r"\bdifferences?\s+between\b|\bvs\.?\b|\bversus\b|\bcompared\s+(?:to|with)\b",
    re.IGNORECASE,
)

# The cue itself plus the question scaffolding around it, so splitting on this
# leaves the bare concepts rather than "What's the difference between a copay".
_COMPARISON_SPLIT_RE = re.compile(
    r"\b(?:what(?:'s|\s+is|\s+are)?\s+the\s+)?differences?\s+between\b"
    r"|\bvs\.?\b|\bversus\b|\bcompared\s+(?:to|with)\b"
    r"|\s+and\s+|\s+or\s+|\s*,\s*",
    re.IGNORECASE,
)


def _comparison_intents(query: str) -> list[str]:
    """Return one sub-query per side of a comparison, or [] if not a comparison.

    A cross-encoder scores every chunk against the whole query, so for "what's
    the difference between a copay and coinsurance" the coinsurance chunks win
    every slot on lexical weight and the copay definition never clears the
    gate. The model is then asked to contrast two things while being shown
    only one of them — measured producing a fabricated comparison. Retrieving
    for each side separately is what keeps both in context.
    """
    if not _COMPARISON_CUE_RE.search(query):
        return []

    parts = [part.strip(" ,;?!.") for part in _COMPARISON_SPLIT_RE.split(query)]
    parts = [part for part in parts if part]

    return parts if len(parts) >= 2 else []


def _per_intent_results(intents: list[str], pairs: list[tuple[str, str]],
                        rows: dict, budget: int) -> list["RetrievedChunk"]:
    """Give each intent an equal share of the context budget.

    Every chunk is still gated on its own score against a real sub-question,
    so this widens *coverage* across the intents without lowering the bar that
    keeps weak context away from the LLM.
    """
    share = max(1, budget // len(intents))
    merged: dict[str, RetrievedChunk] = {}

    for intent in intents:
        for chunk in _above_gate(rerank(intent, pairs, share), rows):
            existing = merged.get(chunk.chunk_id)
            if existing is None or chunk.score > existing.score:
                merged[chunk.chunk_id] = chunk

    return sorted(merged.values(), key=lambda chunk: chunk.score, reverse=True)


def _dense_search(query: str, top_k: int) -> list[str]:
    query_vector = embed_query(query)

    with get_session() as session:
        distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

        stmt = (
            select(Chunk.chunk_id, distance)
            .order_by(distance)
            .limit(top_k)
        )

        rows = session.execute(stmt).all()

    return [row.chunk_id for row in rows]

def search(query: str, top_k: int | None = None) -> list[RetrievedChunk]:
    """Return the top_k most similar chunks for a user query."""
    if top_k is not None and top_k < 5:
        raise ValueError("Internal Error: Atleast 5 chunks are required for retrieval.")

    query = query.strip()
    if not query:
        logger.warning("empty query received; returning no results")
        return []

    sparse_ids = _sparse_search(query, settings.sparse_top_k)
    dense_ids = _dense_search(query, settings.dense_top_k)
    candidate_ids = list(set(sparse_ids + dense_ids))

    if not candidate_ids:
        logger.info("no candidates for query (len=%d)", len(query))
        return []
    
    with get_session() as session:
        stmt = (
            select(Chunk.chunk_id, Chunk.content, Chunk.source)
            .where(Chunk.chunk_id.in_(candidate_ids))
        )

        rows = {row.chunk_id: row for row in session.execute(stmt).all()}

    required_top_k_chunks = top_k or settings.rerank_top_k

    pairs = [(cid, rows[cid].content) for cid in rows]
    ranked = rerank(query, pairs, required_top_k_chunks)
    relevant = _above_gate(ranked, rows)
    matched_as_whole = bool(relevant)

    # Only if the query as a whole matched nothing: retry against its parts.
    # Making this a fallback rather than the default keeps every currently
    # working query byte-for-byte unchanged — taking a best-of score across
    # subqueries can only raise scores, which would otherwise let weak chunks
    # past the relevance gate that guards against hallucination.
    decomposed = []
    intents = _comparison_intents(query)

    if intents:
        # A comparison needs every side present, so per-intent retrieval is the
        # primary strategy here rather than a fallback. Merged with the
        # whole-query hits so nothing that already ranked well is lost.
        by_id = {chunk.chunk_id: chunk for chunk in relevant}
        for chunk in _per_intent_results(intents, pairs, rows, required_top_k_chunks):
            existing = by_id.get(chunk.chunk_id)
            if existing is None or chunk.score > existing.score:
                by_id[chunk.chunk_id] = chunk
        relevant = sorted(by_id.values(), key=lambda chunk: chunk.score, reverse=True)
    elif not matched_as_whole:
        decomposed = _subqueries(query)
        if decomposed:
            relevant = _above_gate(
                _best_scores_across(decomposed, pairs, required_top_k_chunks), rows
            )

    logger.info(
        "hybrid search: %d sparse + %d dense -> %d candidates -> %d reranked -> "
        "%d relevant (%d subqueries tried)",
        len(sparse_ids), len(dense_ids), len(candidate_ids), len(ranked),
        len(relevant), len(decomposed) if not matched_as_whole else 0,
    )

    return relevant


def _above_gate(ranked: list[tuple[str, float]], rows: dict) -> list[RetrievedChunk]:
    """Convert reranker logits to (0,1) relevance and drop anything below the gate."""
    results = [
        RetrievedChunk(
            chunk_id=cid,
            content=rows[cid].content,
            source=rows[cid].source,
            score=1 / (1 + math.exp(-float(raw_score))),   # logit → (0,1), order preserved
        )
        for cid, raw_score in ranked
    ]

    return [r for r in results if r.score >= settings.min_relevance_score]