"""Tests for the HealthCare.gov source and its HTML→markdown conversion.

The staleness filter gets the most attention here: it is the one piece whose
failure is silently harmful rather than loud. Ingesting a page titled "for
the 2016 tax year only" means confidently answering a live question with
rules that no longer exist.
"""
import datetime as dt
import json
from unittest.mock import patch

import pytest
import requests

from src.ingestion.html_text import html_to_markdown
from src.ingestion.sources.healthcare_gov import HealthCareGovSource, _is_stale

# Staleness filter

@pytest.mark.parametrize("title", [
    "Health coverage exemptions for the 2016 tax year only",
    "Health coverage exemptions for the 2017 tax year only",
    "2019 health coverage & your federal taxes",
])
def test_is_stale_rejects_titles_naming_an_expired_year(title):
    assert _is_stale(title, today=dt.date(2026, 9, 7))


@pytest.mark.parametrize("title", [
    "2025 health coverage & your federal taxes",
    "2026 health coverage & your federal taxes",
])
def test_is_stale_keeps_the_current_and_prior_year(title):
    """Prior-year tax content is still filed during the current year."""
    assert not _is_stale(title, today=dt.date(2026, 9, 7))


def test_is_stale_keeps_undated_evergreen_titles():
    assert not _is_stale("How to appeal an insurance company decision", today=dt.date(2026, 9, 7))
    assert not _is_stale("Deductible", today=dt.date(2026, 9, 7))


def test_is_stale_judges_a_year_range_by_its_most_recent_year():
    assert not _is_stale("Coverage rules for 2019 and 2025", today=dt.date(2026, 9, 7))


def test_is_stale_moves_with_the_calendar():
    """The cutoff is relative, so the filter doesn't rot as years pass."""
    title = "2025 health coverage & your federal taxes"

    assert not _is_stale(title, today=dt.date(2026, 1, 1))
    assert _is_stale(title, today=dt.date(2030, 1, 1))


# HTML → markdown

def test_html_to_markdown_extracts_paragraph_text():
    assert html_to_markdown("<p>A deductible is what you pay first.</p>") == (
        "A deductible is what you pay first."
    )


def test_html_to_markdown_separates_block_elements():
    result = html_to_markdown("<p>First para.</p><p>Second para.</p>")

    assert "First para." in result
    assert "Second para." in result
    assert "First para.Second para." not in result


def test_html_to_markdown_preserves_headings_as_markdown():
    result = html_to_markdown("<h2>Cost sharing</h2><p>Details here.</p>")

    assert "## Cost sharing" in result


def test_html_to_markdown_renders_list_items_as_bullets():
    result = html_to_markdown("<ul><li>Copayment</li><li>Coinsurance</li></ul>")

    assert "- Copayment" in result
    assert "- Coinsurance" in result


def test_html_to_markdown_keeps_link_text_and_drops_markup():
    result = html_to_markdown('<p>See <a href="/glossary/deductible">deductible</a> for more.</p>')

    assert "deductible" in result
    assert "href" not in result
    assert "<a" not in result


def test_html_to_markdown_decodes_entities():
    assert "you'll" in html_to_markdown("<p>you&#8217;ll</p>") or "you’ll" in html_to_markdown(
        "<p>you&#8217;ll</p>"
    )


def test_html_to_markdown_drops_script_and_style_content():
    result = html_to_markdown("<p>Real text.</p><script>var x = 'tracking';</script>")

    assert "Real text." in result
    assert "tracking" not in result


def test_html_to_markdown_handles_empty_input():
    assert html_to_markdown("") == ""


# fetch()

def _ok_response(payload):
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode("utf-8")
    return response


def test_fetch_writes_each_collection(tmp_path):
    payloads = {
        "glossary": {"glossary": [{"title": "Deductible", "content": "<p>Pay first.</p>"}]},
        "articles": {"articles": [{"title": "How to appeal", "content": "<p>Steps.</p>"}]},
    }

    def fake_get(url, **kwargs):
        collection = url.rsplit("/", 1)[-1].removesuffix(".json")
        return _ok_response(payloads[collection])

    with patch("src.ingestion.sources.healthcare_gov.RAW", tmp_path), \
         patch("src.ingestion.sources.healthcare_gov.requests.get", side_effect=fake_get):
        HealthCareGovSource().fetch()

    assert json.loads((tmp_path / "hcg_glossary.json").read_text())["glossary"][0]["title"] == (
        "Deductible"
    )
    assert (tmp_path / "hcg_articles.json").exists()


def test_fetch_skips_collections_already_downloaded(tmp_path):
    (tmp_path / "hcg_glossary.json").write_text('{"glossary": []}')
    (tmp_path / "hcg_articles.json").write_text('{"articles": []}')

    with patch("src.ingestion.sources.healthcare_gov.RAW", tmp_path), \
         patch("src.ingestion.sources.healthcare_gov.requests.get") as mock_get:
        HealthCareGovSource().fetch()

    mock_get.assert_not_called()


def test_fetch_does_not_write_a_malformed_response_to_disk(tmp_path):
    """A truncated or error response must not look like a good download later."""
    with patch("src.ingestion.sources.healthcare_gov.RAW", tmp_path), \
         patch("src.ingestion.sources.healthcare_gov.requests.get",
               return_value=_ok_response({"unexpected": "shape"})):
        HealthCareGovSource().fetch()

    assert not (tmp_path / "hcg_glossary.json").exists()


def test_fetch_survives_a_network_error(tmp_path):
    """One failing collection must not abort the whole ingest run."""
    with patch("src.ingestion.sources.healthcare_gov.RAW", tmp_path), \
         patch("src.ingestion.sources.healthcare_gov.requests.get",
               side_effect=requests.ConnectionError("boom")):
        HealthCareGovSource().fetch()  # must not raise

    assert not list(tmp_path.iterdir())


# normalize()

def _write_raw(tmp_path, glossary=(), articles=()):
    (tmp_path / "hcg_glossary.json").write_text(json.dumps({"glossary": list(glossary)}))
    (tmp_path / "hcg_articles.json").write_text(json.dumps({"articles": list(articles)}))


def test_normalize_writes_markdown_with_a_title_heading(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    _write_raw(raw, glossary=[{"title": "Deductible", "content": "<p>What you pay first.</p>"}])

    with patch("src.ingestion.sources.healthcare_gov.RAW", raw), \
         patch("src.ingestion.sources.healthcare_gov.MARKDOWN", md):
        HealthCareGovSource().normalize()

    written = (md / "hcg_glossary_Deductible.md").read_text()
    assert written.startswith("# Deductible")
    assert "What you pay first." in written


def test_normalize_excludes_stale_articles(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    _write_raw(raw, articles=[
        {"title": "Health coverage exemptions for the 2016 tax year only",
         "content": "<p>Old rules.</p>"},
        {"title": "How to appeal a decision", "content": "<p>Current rules.</p>"},
    ])

    with patch("src.ingestion.sources.healthcare_gov.RAW", raw), \
         patch("src.ingestion.sources.healthcare_gov.MARKDOWN", md):
        HealthCareGovSource().normalize()

    written = {p.name for p in md.iterdir()}
    assert "hcg_article_How_to_appeal_a_decision.md" in written
    assert not any("2016" in name for name in written)


def test_normalize_skips_entries_with_no_usable_content(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    _write_raw(raw, glossary=[
        {"title": "Empty term", "content": ""},
        {"title": "", "content": "<p>No title.</p>"},
        {"title": "Real term", "content": "<p>A definition.</p>"},
    ])

    with patch("src.ingestion.sources.healthcare_gov.RAW", raw), \
         patch("src.ingestion.sources.healthcare_gov.MARKDOWN", md):
        HealthCareGovSource().normalize()

    assert {p.name for p in md.iterdir()} == {"hcg_glossary_Real_term.md"}


def test_normalize_tolerates_a_missing_raw_file(tmp_path):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()

    with patch("src.ingestion.sources.healthcare_gov.RAW", raw), \
         patch("src.ingestion.sources.healthcare_gov.MARKDOWN", md):
        HealthCareGovSource().normalize()  # must not raise


# chunk_documents()

def _normalize_then_chunk(tmp_path, glossary=(), articles=(), chunk_size=350):
    raw, md = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    _write_raw(raw, glossary=glossary, articles=articles)

    with patch("src.ingestion.sources.healthcare_gov.RAW", raw), \
         patch("src.ingestion.sources.healthcare_gov.MARKDOWN", md), \
         patch("src.ingestion.sources.healthcare_gov.settings") as mock_settings:
        mock_settings.chunk_size = chunk_size
        mock_settings.chunk_overlap = 10

        source = HealthCareGovSource()
        source.normalize()
        return source.chunk_documents()


def test_glossary_term_is_never_split(tmp_path):
    """A definition split across chunks answers nothing on its own."""
    long_definition = "<p>" + ("This clause explains the term at length. " * 60) + "</p>"

    chunks = _normalize_then_chunk(
        tmp_path,
        glossary=[{"title": "Out-of-pocket maximum/limit", "content": long_definition}],
    )

    assert len(chunks) == 1
    assert chunks[0]["metadata"]["doc_type"] == "healthcare_gov_glossary"


def test_glossary_chunk_text_leads_with_the_term(tmp_path):
    chunks = _normalize_then_chunk(
        tmp_path, glossary=[{"title": "Coinsurance", "content": "<p>A share of costs.</p>"}]
    )

    assert chunks[0]["text"].startswith("Coinsurance:")
    assert "Health insurance glossary" in chunks[0]["contextualized_text"]


def test_articles_are_split_and_carry_their_title(tmp_path):
    body = "<p>" + ("Appeal steps explained in detail. " * 80) + "</p>"

    chunks = _normalize_then_chunk(
        tmp_path, articles=[{"title": "How to appeal a decision", "content": body}], chunk_size=60
    )

    assert len(chunks) > 1
    assert all(c["metadata"]["doc_type"] == "healthcare_gov_article" for c in chunks)
    assert all(c["contextualized_text"].startswith("How to appeal a decision") for c in chunks)


def test_article_chunks_track_headings_as_sections(tmp_path):
    body = (
        "<p>Intro paragraph.</p>"
        "<h2>Filing an internal appeal</h2>"
        "<p>" + ("Send the form to your insurer. " * 40) + "</p>"
    )

    chunks = _normalize_then_chunk(
        tmp_path, articles=[{"title": "Appeals", "content": body}], chunk_size=40
    )

    assert "Filing an internal appeal" in {c["metadata"]["section"] for c in chunks}


def test_chunk_ids_are_unique_across_both_collections(tmp_path):
    """A glossary term and an article can share a title without colliding."""
    chunks = _normalize_then_chunk(
        tmp_path,
        glossary=[{"title": "Appeal", "content": "<p>A request to reconsider.</p>"}],
        articles=[{"title": "Appeal", "content": "<p>How to file one.</p>"}],
    )

    ids = [c["metadata"]["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)) == 2
