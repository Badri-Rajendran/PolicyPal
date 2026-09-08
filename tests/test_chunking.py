from unittest.mock import patch

import pytest

from src.ingestion.chunk import _assert_unique_chunk_ids
from src.ingestion.chunking import (
    _MAX_TITLE_IN_ID,
    count_tokens,
    detect_has_code,
    detect_has_math,
    detect_has_table,
    make_chunk,
    make_chunk_id,
    make_recursive_splitter,
    sanitize_name,
)
from src.ingestion.sources.wikipedia import WikipediaSource


def test_count_tokens_approximates_word_count():
    assert count_tokens("one two three four") == int(4 * 1.35)


def test_detect_has_math():
    assert detect_has_math(r"the formula is \frac{1}{2}")
    assert not detect_has_math("plain sentence with no formulas")


def test_detect_has_code():
    assert detect_has_code("```python\nprint(1)\n```")
    assert not detect_has_code("no code here")


def test_detect_has_table():
    table = "| a | b |\n|---|---|\n| 1 | 2 |"
    assert detect_has_table(table)
    assert not detect_has_table("a | b without a separator row")


def test_sanitize_name_collapses_punctuation():
    assert sanitize_name("Renters' insurance") == "Renters_insurance"
    assert sanitize_name("Long-term care insurance") == "Long_term_care_insurance"


def test_make_chunk_id_is_readable_for_ordinary_titles():
    assert make_chunk_id("wikipedia", "Health_insurance", 7) == "wikipedia_Health_insurance_s0_c07"


def test_make_chunk_id_disambiguates_titles_that_share_a_long_prefix():
    """A truncated title must not collide — chunk_id has a unique index."""
    shared = "A" * _MAX_TITLE_IN_ID
    first = make_chunk_id("healthcare_gov", shared + "_first_variant", 0)
    second = make_chunk_id("healthcare_gov", shared + "_second_variant", 0)

    assert first != second
    assert len(first) <= 255
    assert len(second) <= 255


def test_make_chunk_id_is_namespaced_by_source():
    """Two sources holding a same-named document must not collide."""
    assert make_chunk_id("wikipedia", "Deductible", 0) != make_chunk_id(
        "healthcare_gov", "Deductible", 0
    )


def test_make_chunk_populates_the_metadata_contract():
    chunk = make_chunk(
        text="A deductible is what you pay first.",
        contextualized_text="Health insurance\nA deductible is what you pay first.",
        chunk_id="wikipedia_Health_insurance_s0_c00",
        source_file="wiki_Health_insurance.txt",
        doc_type="wikipedia",
        title="Health insurance",
        section="Health insurance",
        chunk_index=0,
    )

    assert chunk["text"] == "A deductible is what you pay first."
    assert chunk["metadata"]["doc_type"] == "wikipedia"
    assert chunk["metadata"]["token_count"] == count_tokens(chunk["text"])
    assert chunk["metadata"]["language"] == "en"
    assert chunk["metadata"]["is_abstract"] is False


def test_assert_unique_chunk_ids_rejects_duplicates():
    chunks = [
        {"metadata": {"chunk_id": "a"}},
        {"metadata": {"chunk_id": "a"}},
    ]

    with pytest.raises(ValueError, match="duplicate chunk_id"):
        _assert_unique_chunk_ids(chunks)


def test_assert_unique_chunk_ids_accepts_distinct_ids():
    _assert_unique_chunk_ids([{"metadata": {"chunk_id": "a"}}, {"metadata": {"chunk_id": "b"}}])


def test_make_recursive_splitter_respects_configured_size():
    splitter = make_recursive_splitter(chunk_size=20, chunk_overlap=5)
    text = " ".join(f"word{i}" for i in range(200))

    pieces = splitter.split_text(text)

    assert len(pieces) > 1
    assert all(count_tokens(p) <= 30 for p in pieces)


def test_chunk_article_prefixes_title_for_contextual_retrieval():
    with patch("src.ingestion.sources.wikipedia.settings") as mock_settings:
        mock_settings.chunk_size = 60
        mock_settings.chunk_overlap = 10

        chunks = WikipediaSource()._chunk_article(
            "# Health insurance\n\nA deductible is the amount you pay before coverage starts.",
            "Health insurance",
        )

    assert chunks
    assert all(c["contextualized_text"].startswith("Health insurance") for c in chunks)
    # The stored text stays raw — only the indexed text carries the prefix.
    assert not chunks[0]["text"].startswith("Health insurance\n")


def test_chunk_article_tracks_sections_into_contextualized_text():
    # The lead must be long enough to fill its own chunk, so that the section
    # line starts the next one — that's the only position the tracker reads.
    body = (
        "# Health insurance\n\n"
        + "Lead paragraph about coverage generally. " * 20
        + "\n\nCost sharing\n\n"
        + "A deductible is the amount you pay before the plan starts paying. " * 12
    )

    with patch("src.ingestion.sources.wikipedia.settings") as mock_settings:
        mock_settings.chunk_size = 40
        mock_settings.chunk_overlap = 5

        chunks = WikipediaSource()._chunk_article(body, "Health insurance")

    sections = {c["metadata"]["section"] for c in chunks}
    assert "Cost sharing" in sections


def test_chunk_article_metadata_identifies_the_source_file():
    with patch("src.ingestion.sources.wikipedia.settings") as mock_settings:
        mock_settings.chunk_size = 60
        mock_settings.chunk_overlap = 10

        chunks = WikipediaSource()._chunk_article("# Pet insurance\n\nCovers vet bills.", "Pet insurance")

    assert chunks[0]["metadata"]["source_file"] == "wiki_Pet_insurance.txt"
    assert chunks[0]["metadata"]["doc_type"] == "wikipedia"
