from src.policypal.config import settings
from .logging import get_logger

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from sentence_transformers import SentenceTransformer

from functools import lru_cache


logger = get_logger(__name__)

def _resolve_device() -> str:
    '''Pick the compute device. "auto" -> best available (mps on Apple Silicon).'''
    if settings.device != "auto":
        return settings.device
    
    import torch

    if torch.cuda.is_available():   # NVidia GPU
        return "cuda"
    if torch.backends.mps.is_available():   #Apple Silicon GPU
        return "mps"
    
    return "cpu"

@lru_cache
def _model():
    '''Load the embedding model once per process (cached).'''
    device = _resolve_device()
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
