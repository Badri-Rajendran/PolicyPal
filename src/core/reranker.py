from functools import lru_cache
from sentence_transformers import CrossEncoder

from .logging import get_logger
from src.policypal.config import settings



logger = get_logger(__name__)


@lru_cache
def _reranker() -> CrossEncoder:
    logger.info("loading reranker %s", settings.reranker_model)
    return CrossEncoder(settings.reranker_model)


def rerank(query: str, candidates: list[tuple[str, str]], top_k: int) -> list[tuple[str, float]]:
    
    if not candidates:
        return []
    
    pairs = [(query, text) for _, text in candidates]
    scores = _reranker().predict(pairs)

    ranked = sorted(zip((c[0] for c in candidates), scores), key=lambda x: x[1], reverse=True)

    return ranked[:top_k]

    
