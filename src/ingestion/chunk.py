"""Phase 3: chunk every registered source and build the shared BM25 index.

Chunking *strategy* belongs to each source (see `sources/`), because it
depends on document shape — an atomic glossary definition and a long prose
article want different treatment. This module only orchestrates: collect
chunks from each source, write them to one JSONL file, and index them
together so retrieval searches the whole corpus at once.
"""
import json
from collections import Counter

from src.core.logging import get_logger

from .chunking import build_and_store_index
from .constants import CHUNKS_DIR
from .sources import SOURCES

logger = get_logger(__name__)


def execute() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []

    for source in SOURCES:
        all_chunks.extend(source.chunk_documents())

    if not all_chunks:
        # BM25Okapi raises an opaque division error on an empty corpus. Fail
        # here with something actionable instead: this means the fetch or
        # normalize phase produced nothing, not that chunking is broken.
        raise ValueError(
            "No chunks produced by any source — run the fetch and normalize "
            "phases first (`make ingest`), or check that data/corpus/markdown "
            "is populated."
        )

    _assert_unique_chunk_ids(all_chunks)

    output_path = CHUNKS_DIR / "all_chunks.jsonl"

    chunk_texts = []
    chunk_ids = []

    with output_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            # BM25 indexes the contextualized text (title/section-prefixed);
            # the raw chunk["text"] is what gets stored and shown as the source.
            chunk_texts.append(chunk["contextualized_text"])
            chunk_ids.append(chunk["metadata"]["chunk_id"])
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    build_and_store_index(chunk_texts, chunk_ids)

    print(f"\nWrote {len(all_chunks)} chunks to {output_path}")

    _print_summary(all_chunks)


def _assert_unique_chunk_ids(chunks: list[dict]) -> None:
    """Fail before embedding rather than on the unique index mid-insert.

    Embedding the corpus is the slow part of ingestion; a duplicate id caught
    here costs seconds, the same one caught by Postgres costs the whole run.
    """
    counts = Counter(c["metadata"]["chunk_id"] for c in chunks)
    duplicates = [chunk_id for chunk_id, n in counts.items() if n > 1]

    if duplicates:
        raise ValueError(
            f"{len(duplicates)} duplicate chunk_id(s) across sources, "
            f"first few: {duplicates[:5]}"
        )


def _print_summary(chunks: list[dict]) -> None:
    if not chunks:
        print("\n=== Chunking Summary ===\nNo chunks produced.")
        return

    token_counts = [c["metadata"]["token_count"] for c in chunks]
    by_type = Counter(c["metadata"]["doc_type"] for c in chunks)

    print("\n=== Chunking Summary ===")
    print(f"Total chunks:           {len(chunks)}")

    for doc_type, count in sorted(by_type.items()):
        print(f"  {doc_type:<28} {count}")

    print(f"Average token count:    {sum(token_counts) / len(token_counts):.1f}")
    print(f"Min / Max token count:  {min(token_counts)} / {max(token_counts)}")


if __name__ == "__main__":
    from src.core.logging import setup_logging
    setup_logging()
    execute()
