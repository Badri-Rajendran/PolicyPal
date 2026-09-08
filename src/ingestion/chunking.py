"""Chunking utilities shared by every corpus source.

These live apart from `chunk.py` (which orchestrates the run) so that a
source module can build its own chunks without importing the orchestrator
that imports it back.
"""
import hashlib
import pickle
import re

from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from src.core.logging import get_logger

from .constants import INDEX_DIR

logger = get_logger(__name__)

# Postgres caps chunk_id at 255 chars (see the Chunk model). Titles are
# truncated well below that so the suffix always fits.
_MAX_CHUNK_ID = 255
_MAX_TITLE_IN_ID = 180


# Token counting

def count_tokens(text: str) -> int:
    '''Here token count is approximately taken as 1.35 times the word count in a text'''
    no_of_words = len(text.split())
    return int(no_of_words * 1.35)


# Content feature detection

def detect_has_math(text: str) -> bool:
    return bool(re.search(
        r'\$|\\\w+\{|\\frac|\\sum|\\int|\\alpha|\\beta|\\theta|\\sigma|\\nabla',
        text,
    ))


def detect_has_code(text: str) -> bool:
    return "```" in text


def detect_has_table(text: str) -> bool:
    lines = text.split("\n")
    pipe_lines = [l for l in lines if "|" in l and l.strip().startswith("|")]
    sep_lines  = [l for l in lines if re.match(r"^\s*\|[-: |]+\|\s*$", l)]
    return len(pipe_lines) >= 2 and len(sep_lines) >= 1


def sanitize_name(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name).strip("_")


# Splitter factories

def make_recursive_splitter(
    chunk_size: int,
    chunk_overlap: int,
    separators: list[str] | None = None,
) -> RecursiveCharacterTextSplitter:
    """Build a token-aware RecursiveCharacterTextSplitter."""
    if separators is None:
        # Markdown-appropriate order: headings, code fences, blank lines, sentences
        separators = ["\n#{1,6} ", "```\n", "\n\n", "\n", "\\. ", " ", ""]

    return RecursiveCharacterTextSplitter(
        separators=separators,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=count_tokens,
        is_separator_regex=True,
    )


def make_chunk_id(source_name: str, sanitized_title: str, chunk_idx: int) -> str:
    """Build a unique, readable chunk id, bounded to the column width.

    A long title is truncated and disambiguated with a digest of the full
    title, so two documents sharing a 180-char prefix can't collide on the
    unique index and abort an ingest run partway through.
    """
    if len(sanitized_title) > _MAX_TITLE_IN_ID:
        digest = hashlib.blake2b(sanitized_title.encode("utf-8"), digest_size=4).hexdigest()
        sanitized_title = f"{sanitized_title[:_MAX_TITLE_IN_ID]}_{digest}"

    chunk_id = f"{source_name}_{sanitized_title}_s0_c{chunk_idx:02d}"

    if len(chunk_id) > _MAX_CHUNK_ID:
        raise ValueError(f"chunk_id too long ({len(chunk_id)} chars): {chunk_id}")

    return chunk_id


def make_chunk(
    *,
    text: str,
    contextualized_text: str,
    chunk_id: str,
    source_file: str,
    doc_type: str,
    title: str,
    section: str,
    chunk_index: int,
    is_abstract: bool = False,
) -> dict:
    """Assemble one chunk record in the shape `embed.py` expects.

    Every source builds chunks through here so the metadata contract stays
    in one place rather than being restated per source.
    """
    return {
        "text": text,
        "contextualized_text": contextualized_text,
        "metadata": {
            "chunk_id":    chunk_id,
            "source_file": source_file,
            "doc_type":    doc_type,
            "title":       title,
            "language":    "en",
            "section":     section,
            "chunk_index": chunk_index,
            "token_count": count_tokens(text),
            "is_abstract": is_abstract,
            "has_math":    detect_has_math(text),
            "has_code":    detect_has_code(text),
            "has_table":   detect_has_table(text),
        },
    }


def build_and_store_index(texts: list[str], chunk_ids: list[str]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    index_file_path = INDEX_DIR / "bm25.pkl"

    tokenized_texts = [text.lower().split() for text in texts]

    bm25 = BM25Okapi(tokenized_texts)

    with index_file_path.open("wb") as file:
        pickle.dump({
            "bm25": bm25,
            "chunk_ids": chunk_ids,
            "texts": texts,
        },
        file)

    logger.info(f"BM25 index -> {len(tokenized_texts)} docs saved.")
