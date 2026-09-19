"""The search_plans boundary (ADR 0010).

Arguments are model-generated, so they are untrusted: nothing invalid may
reach the database or CMS, and nothing rejected may be echoed back or logged,
because the rejected value may be the user's ZIP code.
"""
import json
import logging
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.services.plan_coverage import PlanCoverage
from src.services.plan_search import CountyOption, PlanResult, PlanSearchResult
from src.services.profile import PlanProfile
from src.services.retrieval import RetrievedChunk
from src.services.tools import run_tool

_NULLS = dict.fromkeys(
    ("zip_code", "age", "metal_level", "plan_type", "max_deductible", "county_fips", "sort_by")
)


def _args(**overrides) -> str:
    return json.dumps(_NULLS | overrides)


@pytest.mark.parametrize(("raw", "rejected"), [
    (_args(zip_code="7580A", age=34), "7580A"),
    (_args(zip_code="758011", age=34), "758011"),
    (_args(zip_code="75801", age=-1), "-1"),
    (_args(zip_code="75801", age=121), "121"),
    # Strict: a numeric string is not an age.
    (_args(zip_code="75801", age="34"), '"34"'),
    (_args(zip_code="75801", age=34, metal_level="Diamond"), "Diamond"),
    (_args(zip_code="75801", age=34, county_fips="Tulsa"), "Tulsa"),
    (_args(zip_code="75801", age=34, dob="1990-01-01"), "1990-01-01"),
    ("zip 75801 age 34", "75801"),
])
def test_invalid_arguments_touch_nothing_and_are_not_echoed(raw, rejected, caplog):
    with patch("src.services.tools.get_session") as session, caplog.at_level(logging.DEBUG):
        outcome = run_tool("search_plans", raw)

    session.assert_not_called()
    assert json.loads(outcome.content)["status"] == "invalid_arguments"
    assert rejected not in outcome.content
    assert rejected not in caplog.text


@pytest.mark.parametrize(("overrides", "missing"), [
    ({}, ("zip_code", "age")),
    ({"zip_code": "75801"}, ("age",)),
    ({"age": 34}, ("zip_code",)),
])
def test_a_missing_zip_or_age_is_asked_for_not_guessed(overrides, missing):
    with patch("src.services.tools.get_session") as session:
        outcome = run_tool("search_plans", _args(**overrides))

    session.assert_not_called()
    assert json.loads(outcome.content) == {"status": "needs_input", "missing": list(missing)}
    assert outcome.needs_input == missing


def test_a_failing_search_is_a_result_not_an_exception(caplog):
    """An exception here would escape the route's OpenAI handler, fail the
    request and roll back the spend it recorded. A database error's text
    carries its bound parameters, so only the type is logged."""
    with patch("src.services.tools.search_plans", side_effect=RuntimeError("zipcode = '75801'")), \
         patch("src.services.tools.get_session"), caplog.at_level(logging.DEBUG):
        outcome = run_tool("search_plans", _args(zip_code="75801", age=34))

    assert json.loads(outcome.content) == {"status": "error"}
    assert "75801" not in caplog.text


def test_an_unknown_tool_is_refused():
    with patch("src.services.tools.get_session") as session:
        outcome = run_tool("delete_everything", "{}")

    session.assert_not_called()
    assert json.loads(outcome.content)["status"] == "error"


def _result_plan(plan_id, *, live, drug=None, sbc_status="ok"):
    return PlanResult(
        hios_plan_id=plan_id, plan_year=2026, name="Plan", issuer="Issuer", metal_level="Bronze",
        plan_type="HMO", monthly_premium=Decimal("620.26") if live else None,
        premium_reference=Decimal("535.35"), deductible=Decimal("0.00"), drug_deductible=drug,
        out_of_pocket_max=Decimal("10600.00"), hsa_eligible=False, quality_rating=None,
        sbc_status=sbc_status,
    )


def test_the_model_reads_each_deductible_by_what_it_covers():
    """Live, a null drug_deductible was read as "live price unavailable", and
    a plan's $0 medical deductible as its whole deductible — the plan also
    had a $5,500 drug one. Fields are named, never null, to leave no reading."""
    result = PlanSearchResult(
        "ok", total_matching=2, plan_year=2026, county=CountyOption("48001", "Anderson", "TX"),
        plans=(_result_plan("11111TX0010001", live=True, drug=Decimal("5500.00")),
               _result_plan("11111TX0010002", live=False)),
    )
    with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
        outcome = run_tool("search_plans", _args(zip_code="75801", age=34))

    split, combined = json.loads(outcome.content)["plans"]
    assert (split["medical_deductible"], split["drug_deductible"]) == ("0.00", "5500.00")
    assert "deductible" not in split
    assert combined["deductible"] == "0.00"
    assert "drug_deductible" not in combined
    # An unpriced plan says whose premium its figure is; a priced one has no second figure.
    assert combined["monthly_premium"] is None
    assert combined["reference_premium_age_27"] == "535.35"
    assert "reference_premium_age_27" not in split
    assert "75801" not in outcome.content
    assert outcome.plans == result.plans


def test_a_search_result_says_whether_each_plans_sbc_can_be_read_and_why_not():
    """ADR 0017: known before plan_coverage is called, in plain words, never the stored detail."""
    result = PlanSearchResult(
        "ok", total_matching=3, plan_year=2026, county=CountyOption("48001", "Anderson", "TX"),
        plans=(_result_plan("11111TX0010001", live=True),
               _result_plan("11111TX0010002", live=True, sbc_status="not_pdf"),
               _result_plan("11111TX0010003", live=True, sbc_status="no_link")),
    )
    with patch("src.services.tools.search_plans", return_value=result), patch("src.services.tools.get_session"):
        outcome = run_tool("search_plans", _args(zip_code="75801", age=34))

    readable, challenged, unlisted = json.loads(outcome.content)["plans"]
    assert readable["sbc_readable"] is True
    assert "sbc_missing_reason" not in readable
    assert (challenged["sbc_readable"], challenged["sbc_missing_reason"]) == (
        False, "the insurer's link returned a web page, not the document")
    assert unlisted["sbc_missing_reason"] == "HealthCare.gov lists no Summary of Benefits and Coverage for this plan"


# The saved profile (ADR 0012)

_SAVED = PlanProfile(zip_code="75801", age=34, county_fips="48001")


def _searched_with(raw, profile):
    result = PlanSearchResult("no_match", county=CountyOption("48001", "Anderson", "TX"), plan_year=2026)
    with patch("src.services.tools.search_plans", return_value=result) as search, \
         patch("src.services.tools.get_session"):
        outcome = run_tool("search_plans", raw, profile)
    return search.call_args.kwargs if search.called else None, outcome


def test_the_saved_profile_fills_a_search_the_model_left_blank():
    """The model sends nulls; the saved ZIP code and age come from the server,
    so they never pass through the prompt."""
    searched, outcome = _searched_with(_args(), _SAVED)

    assert (searched["zip_code"], searched["age"], searched["county_fips"]) == ("75801", 34, "48001")
    assert "75801" not in outcome.content
    assert "34" not in outcome.content


def test_a_zip_code_or_age_in_the_question_overrides_the_profile_for_that_search():
    for_a_child, _ = _searched_with(_args(age=10), _SAVED)
    elsewhere, _ = _searched_with(_args(zip_code="74103"), _SAVED)

    assert (for_a_child["zip_code"], for_a_child["age"], for_a_child["county_fips"]) == ("75801", 10, "48001")
    # The saved county belongs to the saved ZIP code; another ZIP code resolves its own.
    assert (elsewhere["zip_code"], elsewhere["age"], elsewhere["county_fips"]) == ("74103", 34, None)


def test_without_a_profile_or_a_stated_zip_and_age_the_user_is_asked_to_add_them():
    searched, outcome = _searched_with(_args(), None)

    assert searched is None
    assert outcome.needs_input == ("zip_code", "age")


# plan_coverage (ADR 0014)

def _coverage_args(plan_ids=("12345NH0010001",), question="Is an MRI covered?", **extra) -> str:
    return json.dumps({"plan_ids": list(plan_ids), "question": question, **extra})


@pytest.mark.parametrize("raw", [
    _coverage_args(plan_ids=()),
    _coverage_args(plan_ids=["12345NH0010001"] * 2 + ["12345NH0010002", "12345NH0010003"]),
    _coverage_args(plan_ids=["12345nh0010001"]),
    _coverage_args(plan_ids=["12345NH0010001' OR 1=1"]),
    _coverage_args(question=""),
    _coverage_args(question="x" * 301),
    _coverage_args(zip_code="75801"),
    "MRI for plan 12345NH0010001",
])
def test_invalid_coverage_arguments_touch_nothing(raw):
    with patch("src.services.tools.get_session") as session:
        outcome = run_tool("plan_coverage", raw)

    session.assert_not_called()
    assert json.loads(outcome.content)["status"] == "invalid_arguments"
    assert outcome.chunks == ()


def test_a_failing_coverage_read_is_a_result_not_an_exception(caplog):
    with patch("src.services.tools.coverage_for", side_effect=RuntimeError("hios_plan_id = '12345NH0010001'")), \
         patch("src.services.tools.get_session"), caplog.at_level(logging.DEBUG):
        outcome = run_tool("plan_coverage", _coverage_args())

    assert json.loads(outcome.content) == {"status": "error"}
    assert "12345NH0010001" not in caplog.text


def test_coverage_returns_each_plans_passages_as_data_and_as_citations():
    passage = RetrievedChunk("c1", "If you have a test\nImaging $100", "Gold - Summary of Benefits - If you have a test.pdf", 0.4)
    coverages = [
        PlanCoverage("12345NH0010001", "ok", "Gold", "Example", 2026, "https://sbc.example.com/g.pdf", (passage,)),
        PlanCoverage("12345NH0010002", "unavailable", "Silver", "Example", 2026, "https://sbc.example.com/s.pdf",
                     sbc_status="blocked"),
        PlanCoverage("12345NH0010003", "not_found"),
    ]
    with patch("src.services.tools.coverage_for", return_value=coverages) as read, patch("src.services.tools.get_session"):
        outcome = run_tool("plan_coverage", _coverage_args(
            ["12345NH0010001", "12345NH0010002", "12345NH0010003"]), plan_years={"12345NH0010001": 2026})

    assert read.call_args.args[1:] == (["12345NH0010001", "12345NH0010002", "12345NH0010003"],
                                       "Is an MRI covered?", {"12345NH0010001": 2026})
    rows = json.loads(outcome.content)["plans"]
    assert rows[0]["passages"] == [{"source": passage.source, "text": passage.content}]
    assert rows[1] == {"plan_id": "12345NH0010002", "status": "unavailable", "name": "Silver",
                       "issuer": "Example", "plan_year": 2026, "sbc_url": "https://sbc.example.com/s.pdf",
                       "reason": "the insurer's website doesn't allow automated downloads"}
    assert rows[2] == {"plan_id": "12345NH0010003", "status": "not_found"}
    assert outcome.chunks == (passage,)
