#!/usr/bin/env python3
"""Phase 3: Chunking Pipeline — LangChain-based chunking for all document types.

Strategy per document type:
  Wikipedia        → RecursiveCharacterTextSplitter (paragraph-first,
                       chunk_size=350 tok, overlap=0)
"""
from .constants import CHUNKS_DIR, WIKI_ARTICLES, MARKDOWN, INDEX_DIR
from src.core.logging import get_logger

from langchain_text_splitters import RecursiveCharacterTextSplitter

import json
import re
from pathlib import Path
from rank_bm25 import BM25Okapi
import pickle


logger = get_logger(__name__)

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

def _make_chunk_id(sanitized_title: str, chunk_idx: int) -> str:
    chunk_id = f"wikipedia_{sanitized_title}_s0_c{chunk_idx:02d}"
    if len(chunk_id) > 255:
        raise ValueError(f"chunk_id too long ({len(chunk_id)} chars): {chunk_id}")
    return chunk_id

# Wikipedia article chunking

def chunk_wikipedia(filepath: Path, title: str) -> list[dict]:
    """
    RecursiveCharacterTextSplitter with paragraph-first separators.
    chunk_size=350 tokens, overlap=0.
    Lead paragraph (first block before any section) kept as own chunk.
    """
    text = filepath.read_text(encoding="utf-8")
    sanitized_title = re.sub(r"[^\w]+", "_", title).strip("_")

    # Remove the top-level # heading added in Phase 2
    text = re.sub(r"^#\s+.+\n+", "", text, count=1).strip()

    splitter = make_recursive_splitter(
        chunk_size=350,
        chunk_overlap=0,
        separators=["\n\n", "\\. ", "\n", " ", ""],
    )

    raw_chunks = splitter.split_text(text)

    # Simple section tracker: short lines with no terminal punctuation
    # (Wikipedia section titles are plain-text lines in the processed files)

    _section_title_re = re.compile(r"^[A-Z][^\n.!?]{2,80}$")
    cur_section = title

    chunks: list[dict] = []
    
    for c_idx, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()

        # Update section name if chunk starts with a short title-like line
        first_line = chunk_text.split("\n")[0].strip()

        if count_tokens(first_line) < 15 and _section_title_re.match(first_line):
            cur_section = first_line

        chunk_id = _make_chunk_id(sanitized_title, c_idx)

        chunks.append({
            "text": chunk_text,
            "contextualized_text": "",
            "metadata": {
                "chunk_id":    chunk_id,
                "source_file": f"wiki_{sanitized_title}.txt",
                "doc_type":    "wikipedia",
                "title":       title,
                "language":    "en",
                "section":     cur_section,
                "chunk_index": c_idx,
                "token_count": count_tokens(chunk_text),
                "is_abstract": False,
                "has_math":    detect_has_math(chunk_text),
                "has_code":    detect_has_code(chunk_text),
                "has_table":   detect_has_table(chunk_text),
            },
        })

    return chunks


def _build_and_store_index(texts: list[str], chunk_ids: list[str]) -> None:
    INDEX_DIR.mkdir(parents = True, exist_ok = True)

    index_file_path = INDEX_DIR / "bm25.pkl"

    tokenized_texts = [text.lower().split() for text in texts]

    bm25 = BM25Okapi(tokenized_texts)

    with index_file_path.open("wb") as file:
        pickle.dump({
            "bm25": bm25,
            "chunk_ids" : chunk_ids,
            "texts": texts
        }, 
        file)
    
    logger.info(f"BM25 index -> {len(tokenized_texts)} docs saved.")


# Executor

def execute() -> None:
    CHUNKS_DIR.mkdir(exist_ok=True)

    all_chunks: list[dict] = []

    print("\n=== Chunking Wikipedia articles ===")
    
    for title in WIKI_ARTICLES:
        sanitized = re.sub(r"[^\w]+", "_", title).strip("_")
        md_path = MARKDOWN / f"wiki_{sanitized}.md"
        
        if not md_path.exists():
            print(f"  {title}: markdown not found, skipping")
            continue

        chunks = chunk_wikipedia(md_path, title)
        
        print(f"  {title}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    output_path = CHUNKS_DIR / "all_chunks.jsonl"

    chunk_texts = []
    chunk_ids = []

    with output_path.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            chunk_texts.append(chunk["text"])
            chunk_ids.append(chunk["metadata"]["chunk_id"])
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    _build_and_store_index(chunk_texts, chunk_ids)

    print(f"\nWrote {len(all_chunks)} chunks to {output_path}")
    
    _print_summary(all_chunks)


def _print_summary(chunks: list[dict]) -> None:
    token_counts: list[int] = []
    document_count = 0
    
    for c in chunks:
        m = c["metadata"]
        
        document_count += 1
        
        token_counts.append(m["token_count"])
    
    avg = sum(token_counts) / len(token_counts) if token_counts else 0
    
    print("\n=== Chunking Summary ===")
    
    print(f"Total chunks:           {len(chunks)}")
    
    print(f"  {"wikipedia":<22} {document_count}")
    
    print(f"Average token count:    {avg:.1f}")
    print(f"Min / Max token count:  {min(token_counts)} / {max(token_counts)}")


if __name__ == "__main__":
    from src.core.logging import setup_logging
    setup_logging()
    execute()