import math
import pickle as pkl
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

    results = [
        RetrievedChunk(
            chunk_id=cid,
            content=rows[cid].content,
            source=rows[cid].source,
            score=1 / (1 + math.exp(-float(raw_score))),   # logit → (0,1), order preserved
        )
        for cid, raw_score in ranked
    ]

    relevant = [r for r in results if r.score >= settings.min_relevance_score]

    logger.info(
        "hybrid search: %d sparse + %d dense -> %d candidates -> %d reranked -> %d relevant",
        len(sparse_ids), len(dense_ids), len(candidate_ids), len(results), len(relevant),
    )

    return relevant