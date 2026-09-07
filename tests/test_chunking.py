from unittest.mock import patch

from src.ingestion.chunk import (
    _make_chunk_id,
    chunk_wikipedia,
    count_tokens,
    detect_has_code,
    detect_has_math,
    detect_has_table,
    make_recursive_splitter,
)


def test_count_tokens_approximates_word_count():
    assert count_tokens("one two three four") == int(4 * 1.35)


def test_detect_has_math():
    assert detect_has_math(r"the formula is \frac{1}{2}")
    assert not detect_has_math("plain sentence with no formulas")


def test_detect_has_code():
    assert detect_has_code("```python\nprint(1)\n```")
    assert not detect_has_code("no code here")


def test_detect_has_table():
    text = "| a | b |\n| - | - |\n| 1 | 2 |"
    assert detect_has_table(text)
    assert not detect_has_table("just | one pipe line")


def test_make_chunk_id_rejects_overlong_ids():
    import pytest

    with pytest.raises(ValueError):
        _make_chunk_id("x" * 300, 0)


def test_splitter_respects_configured_chunk_size():
    splitter = make_recursive_splitter(chunk_size=10, chunk_overlap=0)
    chunks = splitter.split_text(" ".join(f"word{i}" for i in range(60)))
    assert len(chunks) > 1
    assert all(count_tokens(c) <= 15 for c in chunks)  # small slack for the splitter's own boundaries


def test_chunk_wikipedia_uses_configured_size_and_overlap(tmp_path):
    # Two long paragraphs guarantee a split; distinct sentences let us verify overlap.
    paragraph_a = " ".join(f"AlphaSentence{i} covers this topic." for i in range(30))
    paragraph_b = " ".join(f"BetaSentence{i} covers a different topic." for i in range(30))
    article = f"# Some Insurance Topic\n\n{paragraph_a}\n\n{paragraph_b}\n"

    md_path = tmp_path / "wiki_Some_Insurance_Topic.md"
    md_path.write_text(article, encoding="utf-8")

    with patch("src.ingestion.chunk.settings") as mock_settings:
        mock_settings.chunk_size = 40
        mock_settings.chunk_overlap = 15
        chunks = chunk_wikipedia(md_path, "Some Insurance Topic")

    assert len(chunks) > 1
    # With overlap, the tail of one chunk should reappear at the head of the next.
    first_tail_words = chunks[0]["text"].split()[-5:]
    second_text = chunks[1]["text"]
    assert any(word in second_text for word in first_tail_words)


def test_chunk_wikipedia_prefixes_contextualized_text_with_title(tmp_path):
    md_path = tmp_path / "wiki_Topic.md"
    md_path.write_text("# Health Insurance\n\nThe deductible is paid before coverage begins.\n", encoding="utf-8")

    with patch("src.ingestion.chunk.settings") as mock_settings:
        mock_settings.chunk_size = 350
        mock_settings.chunk_overlap = 0
        chunks = chunk_wikipedia(md_path, "Health Insurance")

    # The raw text (what's stored/shown) must stay clean of the title prefix...
    assert not chunks[0]["text"].startswith("Health Insurance")
    # ...while the indexed/embedded text carries it, so a query naming the
    # topic can match a chunk that itself never says "health insurance".
    assert chunks[0]["contextualized_text"].startswith("Health Insurance\n")
    assert "deductible" in chunks[0]["contextualized_text"]


def test_chunk_wikipedia_strips_leading_heading(tmp_path):
    md_path = tmp_path / "wiki_Topic.md"
    md_path.write_text("# Topic\n\nActual content about the topic.\n", encoding="utf-8")

    with patch("src.ingestion.chunk.settings") as mock_settings:
        mock_settings.chunk_size = 350
        mock_settings.chunk_overlap = 0
        chunks = chunk_wikipedia(md_path, "Topic")

    assert len(chunks) == 1
    assert not chunks[0]["text"].startswith("#")
    assert chunks[0]["metadata"]["chunk_id"] == "wikipedia_Topic_s0_c00"
    assert chunks[0]["metadata"]["source_file"] == "wiki_Topic.txt"
