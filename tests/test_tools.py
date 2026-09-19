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

from src.services.plan_search import CountyOption, PlanResult, PlanSearchResult
from src.services.profile import PlanProfile
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


def _result_plan(plan_id, *, live, drug=None):
    return PlanResult(
        hios_plan_id=plan_id, plan_year=2026, name="Plan", issuer="Issuer", metal_level="Bronze",
        plan_type="HMO", monthly_premium=Decimal("620.26") if live else None,
        premium_reference=Decimal("535.35"), deductible=Decimal("0.00"), drug_deductible=drug,
        out_of_pocket_max=Decimal("10600.00"), hsa_eligible=False, quality_rating=None,
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
