"""Coverage answers read one plan's own SBC, for that plan's year (ADR 0014).

Real Postgres through the rolled-back `session` fixture. The cross-encoder is
replaced by one that keeps the stored order, so these tests are about which
chunks can be returned at all, not how they rank.
"""
from unittest.mock import patch

import pytest

from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.services import plan_coverage
from src.services.plan_coverage import PASSAGES_PER_PLAN, coverage_for, source_label

YEAR = 1999
SHARED = "https://sbc.example.com/shared.pdf"


@pytest.fixture(autouse=True)
def _stored_order():
    with patch.object(plan_coverage, "rerank",
                      side_effect=lambda query, candidates, top_k: [(cid, 0.0) for cid, _ in candidates][:top_k]):
        yield


@pytest.fixture
def issuer(session):
    issuer = Issuer(hios_issuer_id="99999", plan_year=YEAR, name="Example Health", state="NH")
    session.add(issuer)
    session.flush()
    return issuer


def _plan(session, issuer, plan_id, url, year=YEAR, name=None):
    session.add(Plan(issuer_id=issuer.id, hios_plan_id=plan_id, plan_year=year, marketing_name=name or plan_id,
                     metal_level="Silver", plan_type="HMO", state="NH", benefits_url=url,
                     hsa_eligible=False, has_national_network=False))
    session.flush()


def _document(session, url, year=YEAR, status="ok", **sections):
    document = SbcDocument(url=url, plan_year=year, status=status)
    session.add(document)
    session.flush()
    for position, (section, text) in enumerate(sections.items()):
        session.add(SbcChunk(document_id=document.id, chunk_id=f"{url}#{year}#{position}",
                             section=section, position=position, content=f"{section}\n{text}"))
    session.flush()


def _texts(coverage):
    return [p.content for p in coverage.passages]


def test_a_plan_gets_only_its_own_documents_passages(session, issuer):
    """The headline case: same issuer, same headings, different numbers."""
    _plan(session, issuer, "99999NH0010001", "https://sbc.example.com/a.pdf")
    _plan(session, issuer, "99999NH0010002", "https://sbc.example.com/b.pdf")
    _document(session, "https://sbc.example.com/a.pdf", test="Imaging $100 copay", er="ER $250")
    _document(session, "https://sbc.example.com/b.pdf", test="Imaging $900 copay", er="ER $999")

    [a] = coverage_for(session, ["99999NH0010001"], "Is an MRI covered?")

    assert a.status == "ok"
    assert _texts(a) == ["test\nImaging $100 copay", "er\nER $250"]


def test_at_most_a_few_passages_per_plan(session, issuer):
    _plan(session, issuer, "99999NH0010001", SHARED)
    _document(session, SHARED, **{f"s{i}": f"text {i}" for i in range(10)})

    [coverage] = coverage_for(session, ["99999NH0010001"], "anything")

    assert len(coverage.passages) == PASSAGES_PER_PLAN


def test_plans_sharing_a_document_are_each_cited_by_name(session, issuer):
    _plan(session, issuer, "99999NH0010001", SHARED, name="Example Silver")
    _plan(session, issuer, "99999NH0010002", SHARED, name="Example Silver Plus")
    _document(session, SHARED, **{"If you have a test": "Imaging $100 copay"})

    first, second = coverage_for(session, ["99999NH0010001", "99999NH0010002"], "MRI?")

    assert first.passages[0].chunk_id == second.passages[0].chunk_id
    assert first.passages[0].source == "Example Silver - Summary of Benefits - If you have a test.pdf"
    assert second.passages[0].source == "Example Silver Plus - Summary of Benefits - If you have a test.pdf"


def test_a_document_for_another_year_is_never_used(session, issuer):
    """Issuers reuse a URL every year: last year's SBC is not this year's plan."""
    _plan(session, issuer, "99999NH0010001", SHARED, year=YEAR)
    _plan(session, issuer, "99999NH0010001", SHARED, year=YEAR + 1)
    _document(session, SHARED, year=YEAR, test="Imaging $100 copay")

    [shown_last_year] = coverage_for(session, ["99999NH0010001"], "MRI?", {"99999NH0010001": YEAR})
    [latest] = coverage_for(session, ["99999NH0010001"], "MRI?")

    assert (shown_last_year.status, shown_last_year.plan_year) == ("ok", YEAR)
    assert (latest.status, latest.plan_year, latest.passages) == ("no_document", YEAR + 1, ())


@pytest.mark.parametrize(("url", "document_status", "expected", "sbc_status"), [
    (None, None, "no_document", "no_link"),
    (SHARED, None, "no_document", "not_read"),
    (SHARED, "blocked", "unavailable", "blocked"),
    (SHARED, "http_error", "unavailable", "http_error"),
    (SHARED, "not_pdf", "unavailable", "not_pdf"),
    (SHARED, "too_large", "unavailable", "too_large"),
    (SHARED, "wrong_year", "unavailable", "wrong_year"),
    (SHARED, "unparseable", "unavailable", "unparseable"),
])
def test_a_plan_without_a_usable_document_says_why(session, issuer, url, document_status, expected, sbc_status):
    """ADR 0017: the precise reason survives, so the answer can give it."""
    _plan(session, issuer, "99999NH0010001", url)
    if document_status:
        _document(session, SHARED, status=document_status)

    [coverage] = coverage_for(session, ["99999NH0010001"], "MRI?")

    assert (coverage.status, coverage.sbc_status, coverage.sbc_url, coverage.passages) == (
        expected, sbc_status, url, ())


def test_a_readable_plan_says_so(session, issuer):
    _plan(session, issuer, "99999NH0010001", SHARED)
    _document(session, SHARED, test="Imaging $100 copay")

    [coverage] = coverage_for(session, ["99999NH0010001"], "MRI?")

    assert (coverage.status, coverage.sbc_status) == ("ok", "ok")


def test_an_unknown_plan_is_not_found(session):
    assert [c.status for c in coverage_for(session, ["00000XX0000000"], "MRI?")] == ["not_found"]


def test_a_catalog_names_stray_spaces_are_not_part_of_its_label():
    assert source_label(" Value Silver ", "If you have a test") == "Value Silver - Summary of Benefits - If you have a test.pdf"


def test_a_long_plan_name_gives_way_so_the_label_fits():
    label = source_label("A" * 400, "If you have a test")

    assert len(label) == 300
    assert label.endswith(" - Summary of Benefits - If you have a test.pdf")
