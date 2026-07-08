from src.policypal.config import settings
from .logging import get_logger
from .device import resolve_device

from sentence_transformers import SentenceTransformer

from functools import lru_cache


logger = get_logger(__name__)

@lru_cache
def _model():
    '''Load the embedding model once per process (cached).'''
    device = resolve_device()
    logger.info("loading embedding model %s on %s", settings.embedding_model, device)
    return SentenceTransformer(settings.embedding_model, device=device)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        logger.warning("No chunks in the given input, skipping the embedding.")
        return []

    embedding_model = _model()
    embedding_vectors = embedding_model.encode(
        texts, 
        normalize_embeddings=True, 
        show_progress_bar=True,
        convert_to_numpy=True
    )

    return embedding_vectors.tolist()


def embed_query(query: str) -> list[float]:
    query = query.strip()

    if not query:
        logger.warning("Provide a valid non-empty query. Skipping query embedding.")
        return []

    prefixed_query_text = f"{settings.query_prefix}{query}"

    embedding_model = _model()
    embedding_vector = embedding_model.encode(
        prefixed_query_text,
        normalize_embeddings= True,
        convert_to_numpy=True
    )

    return embedding_vector.tolist()
