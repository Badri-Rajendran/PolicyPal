# The API only. Ingestion stays on the machine that holds data/ (ADR 0016,
# 0019); nothing in this image fetches or keeps a PDF.
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS builder

# Every base and tool image is pinned by digest, not by tag: a tag can be
# moved to different bytes, and the rest of this repo pins actions by SHA
# and gitleaks by checksum for the same reason.
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies resolve from the lock alone, so this layer is rebuilt only when
# the lock changes — not on every source edit. torch comes from PyTorch's CPU
# index on linux (see pyproject.toml), which leaves out the CUDA libraries.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Both models, at the revisions config.py pins, downloaded once here. A cold
# start then loads them from the image instead of reaching HuggingFace, so a
# HuggingFace outage cannot take the API down and no request waits on a
# 220 MB download.
# The venv's python directly, not `uv run`: `uv run` re-syncs the default
# groups, which pulls the dev dependencies back in after --no-dev removed them.
ENV HF_HOME=/opt/models
RUN JWT_SECRET_KEY=build OPENAI_API_KEY=build DATABASE_URL=postgresql+psycopg://build/build \
    /app/.venv/bin/python -c "\
from sentence_transformers import CrossEncoder, SentenceTransformer; \
from src.policypal.config import settings; \
SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision); \
CrossEncoder(settings.reranker_model, revision=settings.reranker_model_revision)"


FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime

# Nothing here runs as root, and nothing writes to the image.
RUN useradd --create-home --uid 10001 policypal

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/models \
    HF_HUB_OFFLINE=1 \
    LOG_DIR=/tmp/logs

WORKDIR /app

COPY --from=builder --chown=policypal:policypal /app/.venv /app/.venv
COPY --from=builder --chown=policypal:policypal /opt/models /opt/models
COPY --chown=policypal:policypal src/ ./src/
COPY --chown=policypal:policypal migrations/ ./migrations/
COPY --chown=policypal:policypal alembic.ini ./

USER policypal
EXPOSE 8000

# One worker: Flask-Limiter has no shared storage yet, so each worker would
# keep its own counters and the configured limits would multiply (ADR 0022).
# Threads carry the concurrency; the request path waits on OpenAI, not on CPU.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", \
     "--timeout", "120", "--access-logfile", "-", "src.api.main:create_app()"]
