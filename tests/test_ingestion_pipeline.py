"""Tests for the source-agnostic ingestion orchestration and the Wikipedia source.

The orchestrator's failure mode is silence: if it writes a malformed JSONL or
hands the indexer ids that don't line up with its texts, nothing raises —
retrieval just quietly returns the wrong chunks.

What reaches the indexer is checked at the call, not by reading back a stored
index: the orchestrator's job is to hand over the right texts and ids, and
storing them is `build_and_store_index`'s (tested separately).
"""
import json
from unittest.mock import patch

import pytest

from src.ingestion import chunk as chunk_module
from src.ingestion.chunking import make_chunk
from src.ingestion.sources.base import Source
from src.ingestion.sources.wikipedia import WikipediaSource


class _FakeSource(Source):
    def __init__(self, name, chunks):
        self.name = name
        self._chunks = chunks

    def fetch(self) -> None:  # pragma: no cover - not exercised here
        pass

    def normalize(self) -> None:  # pragma: no cover - not exercised here
        pass

    def chunk_documents(self) -> list[dict]:
        return self._chunks


def _chunk(chunk_id, text="Some text about coverage.", doc_type="wikipedia"):
    return make_chunk(
        text=text,
        contextualized_text=f"Context\n{text}",
        chunk_id=chunk_id,
        source_file=f"{chunk_id}.md",
        doc_type=doc_type,
        title="Title",
        section="Title",
        chunk_index=0,
    )


def _run_execute(tmp_path, sources):
    """Runs the orchestrator, returning where chunks were written and what the indexer got."""
    chunks_dir = tmp_path / "chunks"

    with patch.object(chunk_module, "SOURCES", sources), \
         patch.object(chunk_module, "CHUNKS_DIR", chunks_dir), \
         patch.object(chunk_module, "build_and_store_index") as indexer:
        chunk_module.execute()

    return chunks_dir, indexer


# Orchestration

def test_execute_aggregates_chunks_from_every_source(tmp_path):
    sources = [
        _FakeSource("a", [_chunk("a_1"), _chunk("a_2")]),
        _FakeSource("b", [_chunk("b_1", doc_type="healthcare_gov_glossary")]),
    ]

    chunks_dir, _ = _run_execute(tmp_path, sources)

    lines = (chunks_dir / "all_chunks.jsonl").read_text().strip().split("\n")
    ids = [json.loads(line)["metadata"]["chunk_id"] for line in lines]

    assert ids == ["a_1", "a_2", "b_1"]


def test_execute_writes_one_valid_json_object_per_line(tmp_path):
    chunks_dir, _ = _run_execute(tmp_path, [_FakeSource("a", [_chunk("a_1"), _chunk("a_2")])])

    for line in (chunks_dir / "all_chunks.jsonl").read_text().strip().split("\n"):
        record = json.loads(line)
        assert {"text", "contextualized_text", "metadata"} <= record.keys()


def test_execute_indexes_the_contextualized_text_not_the_raw_text(tmp_path):
    """Retrieval depends on this: BM25 searches context, the DB stores raw."""
    _, indexer = _run_execute(tmp_path, [_FakeSource("a", [_chunk("a_1", text="A deductible.")])])

    texts, chunk_ids = indexer.call_args.args
    assert texts == ["Context\nA deductible."]
    assert chunk_ids == ["a_1"]


def test_execute_keeps_index_ids_aligned_with_index_texts(tmp_path):
    """A misalignment here returns the wrong chunk for every BM25 hit."""
    chunks = [_chunk(f"a_{i}", text=f"Text {i}") for i in range(5)]

    _, indexer = _run_execute(tmp_path, [_FakeSource("a", chunks)])

    texts, chunk_ids = indexer.call_args.args
    assert len(texts) == len(chunk_ids) == 5
    for i, chunk_id in enumerate(chunk_ids):
        assert texts[i].endswith(f"Text {i}")
        assert chunk_id == f"a_{i}"


def test_execute_rejects_duplicate_chunk_ids_across_sources(tmp_path):
    """Caught before embedding — the same clash found by Postgres costs the run."""
    sources = [_FakeSource("a", [_chunk("shared")]), _FakeSource("b", [_chunk("shared")])]

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        _run_execute(tmp_path, sources)


def test_execute_fails_clearly_when_no_source_produces_anything(tmp_path):
    """Otherwise BM25Okapi raises an opaque error on the empty corpus."""
    with pytest.raises(ValueError, match="No chunks produced"):
        _run_execute(tmp_path, [_FakeSource("a", [])])


# Wikipedia source

def _normalize_wikipedia(tmp_path, title, raw_text):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    (raw / f"wiki_{title.replace(' ', '_')}.txt").write_text(raw_text, encoding="utf-8")

    with patch("src.ingestion.sources.wikipedia.RAW", raw), \
         patch("src.ingestion.sources.wikipedia.MARKDOWN", md), \
         patch("src.ingestion.sources.wikipedia.WIKI_ARTICLES", [title]):
        WikipediaSource().normalize()

    return md / f"wiki_{title.replace(' ', '_')}.md"


def test_normalize_strips_trailing_apparatus_sections(tmp_path):
    """See also / References / External links are link lists, never answers."""
    raw = (
        "Pet insurance covers veterinary bills.\n\n"
        "== See also ==\nSomething else\n\n"
        "== References ==\nCitation list\n\n"
        "== External links ==\nA link\n"
    )

    written = _normalize_wikipedia(tmp_path, "Pet insurance", raw).read_text()

    assert "covers veterinary bills" in written
    assert "See also" not in written
    assert "References" not in written
    assert "External links" not in written


def test_normalize_strips_citation_markers(tmp_path):
    written = _normalize_wikipedia(
        tmp_path, "Pet insurance", "Pet insurance covers vet bills.[1][23]"
    ).read_text()

    assert "[1]" not in written
    assert "[23]" not in written
    assert "covers vet bills." in written


def test_normalize_adds_a_title_heading(tmp_path):
    written = _normalize_wikipedia(tmp_path, "Pet insurance", "Covers vet bills.").read_text()

    assert written.startswith("# Pet insurance")


def test_normalize_tolerates_a_missing_raw_file(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()

    with patch("src.ingestion.sources.wikipedia.RAW", raw), \
         patch("src.ingestion.sources.wikipedia.MARKDOWN", md), \
         patch("src.ingestion.sources.wikipedia.WIKI_ARTICLES", ["Missing article"]):
        WikipediaSource().normalize()  # must not raise

    assert not list(md.iterdir())


def test_normalize_does_not_reprocess_existing_markdown(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    md.mkdir()
    (raw / "wiki_Pet_insurance.txt").write_text("New content.")
    (md / "wiki_Pet_insurance.md").write_text("# Pet insurance\n\nAlready processed.")

    with patch("src.ingestion.sources.wikipedia.RAW", raw), \
         patch("src.ingestion.sources.wikipedia.MARKDOWN", md), \
         patch("src.ingestion.sources.wikipedia.WIKI_ARTICLES", ["Pet insurance"]):
        WikipediaSource().normalize()

    assert "Already processed." in (md / "wiki_Pet_insurance.md").read_text()


def test_chunk_documents_reads_the_normalized_markdown(tmp_path):
    md = tmp_path / "md"
    md.mkdir()
    (md / "wiki_Pet_insurance.md").write_text("# Pet insurance\n\nCovers veterinary bills.")

    with patch("src.ingestion.sources.wikipedia.MARKDOWN", md), \
         patch("src.ingestion.sources.wikipedia.WIKI_ARTICLES", ["Pet insurance"]), \
         patch("src.ingestion.sources.wikipedia.settings") as mock_settings:
        mock_settings.chunk_size = 350
        mock_settings.chunk_overlap = 50

        chunks = WikipediaSource().chunk_documents()

    assert len(chunks) == 1
    assert "Covers veterinary bills." in chunks[0]["text"]
    assert chunks[0]["metadata"]["chunk_id"].startswith("wikipedia_Pet_insurance")


def test_chunk_documents_skips_articles_with_no_markdown(tmp_path):
    md = tmp_path / "md"
    md.mkdir()

    with patch("src.ingestion.sources.wikipedia.MARKDOWN", md), \
         patch("src.ingestion.sources.wikipedia.WIKI_ARTICLES", ["Pet insurance"]):
        assert WikipediaSource().chunk_documents() == []
