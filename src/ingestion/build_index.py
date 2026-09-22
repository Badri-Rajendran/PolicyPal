"""Rebuild the BM25 index from the chunks already in the database: `make build-index`.

The index is derived data (ADR 0021): everything it needs — each chunk's text
and its id — is a column away. So it can be rebuilt without re-fetching,
re-chunking or re-embedding anything, which is what makes seeding a fresh
database a restore plus one command.

`make ingest` still builds it as the last step of a full run; this is for when
the chunks are already there.
"""
import sys

from sqlalchemy import select

from src.core.db import get_session
from src.core.logging import get_logger, setup_logging
from src.models.chunk import Chunk

from .chunking import build_and_store_index

logger = get_logger(__name__)


def main() -> None:
    setup_logging()
    with get_session() as session:
        rows = session.execute(select(Chunk.chunk_id, Chunk.content).order_by(Chunk.id)).all()

    if not rows:
        sys.exit("No chunks in the database. Run `make ingest` first.")

    build_and_store_index([content for _, content in rows], [chunk_id for chunk_id, _ in rows])
    print(f"BM25 index rebuilt from {len(rows)} chunks.")


if __name__ == "__main__":
    main()
