from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Environment & Logging:

    environment: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "CRITICAL", "ERROR"] = "INFO"
    log_dir: str = "logs/backend"

    # Database PostgreSQL + pgvector

    database_url: str = Field(...,description="SQLAlchemy Postgres URL for connection.")

    # Embedding

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    # Pinned commit, not a mutable branch ref: a model repo can change its
    # weights under an unpinned name, which is a real supply-chain risk for
    # anything downloaded and executed automatically (CWE-494).
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dim: int = 384

    device: Literal["auto", "cpu", "mps", "cuda"] = "auto"

    query_prefix: str = "Represent this sentence for searching relevant passages: "

    # HF Token

    hf_api_key: SecretStr | None = None

    # RAG Chunking

    chunk_size: int = 350
    # ~15% of chunk_size: standard RAG guidance to avoid severing a definition
    # from the qualifying clause right after it (e.g. "deductible" from an
    # exclusion that follows in the next sentence) at a hard chunk boundary.
    chunk_overlap: int = 50

    # Hybrid retrieval
    bm25_index_path: str = "data/corpus/indices/bm25.pkl"

    sparse_top_k: int = 20
    dense_top_k: int = 30

    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_model_revision: str = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
    # Measured across 5/8/10/15 on the coverage eval: answered, evidence, and
    # routing are identical at every value — the extra chunks add no retrieval
    # quality, only citation noise (9.8 sources shown per answer at 15 vs 4.4
    # at 5) and 3x the context a small LLM has to stay grounded in.
    rerank_top_k: int = 5

    # Minimum reranker relevance (sigmoid of cross-encoder logit, 0-1) a chunk
    # must clear to be used as context. Below this the match is treated as
    # noise so the LLM isn't fed distracting content it might hallucinate from.
    min_relevance_score: float = 0.5

    # LLM

    # Hosted (ADR 0008), so there is no revision to pin — the embedding and
    # reranker models above stay local and keep theirs.
    openai_api_key: SecretStr = Field(..., description="OpenAI API key.")
    llm_model: str = "gpt-5-mini"
    # This model reasons before it answers, and the cap covers BOTH the
    # reasoning and the reply — spend it all thinking and the reply comes back
    # empty, with finish_reason "length" and no error. Measured at 64-128
    # reasoning tokens for "low", so these leave room for the reply on top.
    max_output_tokens: int = 512
    # "low" produced the same answers as "medium" for half the reasoning
    # tokens; grounded extraction from supplied context is not a hard problem.
    reasoning_effort: str = "low"
    # A hosted call can hang where an in-process one could not.
    llm_request_timeout: float = 30.0

    # Conversation history (ADR 0005)

    # Prior turns are filled newest-first until this many tokens are used. A
    # turn count behaves badly at both extremes: three long turns crowd out
    # the retrieved context, three one-line turns waste the window.
    history_token_budget: int = 1024
    # A rewritten follow-up is one short question, never prose. Capping the
    # generation is the first of the guards that keep a bad rewrite cheap —
    # but the cap also has to cover reasoning tokens (see max_output_tokens),
    # and _MAX_REWRITE_CHARS is what actually bounds the question's length.
    rewrite_max_output_tokens: int = 192

    # API / Auth

    jwt_secret_key: SecretStr = Field(..., description="Signing key for access tokens.")
    jwt_access_token_expires_minutes: int = 30

    # Only this origin may call the API from a browser.
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings():
    "Returns a Settings object for this project"

    return Settings()


settings = get_settings()
