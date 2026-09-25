"""The CMS Marketplace API client.

HTTP is patched at `src.core.marketplace_api.requests.request` with real
`requests.Response` objects, as in test_sources_healthcare_gov.py. No test
here reaches the network or needs a real key.
"""
import json
from decimal import Decimal
from unittest.mock import patch

import pytest
import requests
from pydantic import SecretStr

from src.core import marketplace_api as core
from src.core.exceptions import MarketplaceApiKeyMissingError
from src.ingestion import marketplace_api
from src.ingestion.marketplace_api import County
from src.policypal.config import settings

KEY = "test-key-do-not-log"


@pytest.fixture(autouse=True)
def _fast_and_keyed():
    with (
        patch.object(settings, "cms_marketplace_api_key", SecretStr(KEY)),
        patch("src.core.marketplace_api.time.sleep"),
    ):
        yield


def _response(status, payload=None, url=f"https://marketplace.api.healthcare.gov/api/v1/x?apikey={KEY}"):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode() if payload is not None else b""
    response.url = url
    return response


def _page(total, ids):
    return _response(200, {"total": total, "plans": [{"id": i} for i in ids]})


def test_an_http_error_never_carries_the_api_key():
    """The key is a query parameter. raise_for_status() would put the full URL
    in the message, and the orchestrator logs that message."""
    with (
        patch("src.core.marketplace_api.requests.request", return_value=_response(500)),
        pytest.raises(requests.HTTPError) as exc,
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)

    assert KEY not in str(exc.value)
    assert "apikey" not in str(exc.value)
    assert "500" in str(exc.value)


def test_a_connection_error_never_carries_the_api_key():
    """requests embeds the URL in connection and timeout errors too, so these
    are re-raised with no chained cause for a traceback to print."""
    leaky = requests.ConnectionError(f"Max retries exceeded with url: /api/v1/plans/search?apikey={KEY}")
    with (
        patch("src.core.marketplace_api.requests.request", side_effect=leaky),
        pytest.raises(requests.RequestException) as exc,
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)

    assert KEY not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__suppress_context__


def test_every_page_is_fetched():
    """Pages are a fixed 10 — `limit` is ignored upstream — so 25 plans take
    offsets 0, 10 and 20. A paging bug here silently drops plans."""
    pages = [_page(25, range(10)), _page(25, range(10, 20)), _page(25, range(20, 25))]
    with patch("src.core.marketplace_api.requests.request", side_effect=pages) as request:
        plans = marketplace_api.county_plans("TX", "48113", "75001", 2026)

    assert [p["id"] for p in plans] == list(range(25))
    assert [call.kwargs["json"]["offset"] for call in request.call_args_list] == [0, 10, 20]


def test_a_failed_page_fails_the_whole_county():
    """A partial list would record the county as selling fewer plans than it
    does. Raising lets the orchestrator skip the county and retry it later."""
    pages = [_page(25, range(10)), _response(503)]
    with (
        patch("src.core.marketplace_api.requests.request", side_effect=pages),
        pytest.raises(requests.HTTPError),
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)


def test_a_truncated_cache_is_refetched_not_fatal(tmp_path):
    """A run killed mid-write must not break every later run: the county list
    is read before any per-county error handling, so a bad cache would stop
    the whole ingest until someone found and deleted the file."""
    cache = tmp_path / "county_zips_2026.json"
    cache.write_text('[{"state": "TX", "coun')
    payload = [{"state": "TX", "counties": [{"name": "Dallas", "fips": "48113", "zips": ["75001"]}]}]

    with (
        patch("src.ingestion.marketplace_api.PLANS_RAW", tmp_path),
        patch("src.core.marketplace_api.requests.request", return_value=_response(200, payload)),
    ):
        assert marketplace_api.county_zips(2026) == [County("TX", "48113", "Dallas", ("75001",))]

    assert json.loads(cache.read_text()) == payload
    assert not list(tmp_path.glob("*.tmp"))


def test_a_zero_premium_means_unpriced_never_free():
    """Verified live: POST /plans answers a plan the county does not sell with
    `premium: 0`, not an error. Read at face value, a plan the user cannot buy
    would be listed as costing nothing."""
    payload = {"plans": [
        {"id": "11111TX0010001", "premium": 620.15},
        {"id": "11111TX0010002", "premium": 0},
        {"id": "99999TX0099999", "premium": 1.0},  # never asked for
    ]}
    with patch("src.core.marketplace_api.requests.request", return_value=_response(200, payload)) as request:
        premiums = core.age_rated_premiums(
            ["11111TX0010001", "11111TX0010002"], age=34, state="TX", countyfips="48001", zipcode="75751", year=2026
        )

    assert premiums == {"11111TX0010001": Decimal("620.15")}
    assert request.call_args.kwargs["json"]["household"] == {"people": [{"age": 34}]}


@pytest.mark.parametrize("key", [None, SecretStr("")])
def test_a_missing_key_fails_before_any_request(key):
    """A blank `CMS_MARKETPLACE_API_KEY=` line is as missing as an absent one."""
    with (
        patch.object(settings, "cms_marketplace_api_key", key),
        patch("src.core.marketplace_api.requests.request") as request,
        pytest.raises(MarketplaceApiKeyMissingError),
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)

    request.assert_not_called()


def test_a_state_the_api_does_not_serve_is_refused_before_any_request():
    """California is priced from filed rates (ADR 0024); asking CMS would spend a request on nothing."""
    with patch.object(core, "request") as request, pytest.raises(ValueError, match="CA is not served"):
        core.age_rated_premiums(["40513CA0010001"], age=40, state="CA", countyfips="06037", zipcode="90012",
                                year=2026)

    request.assert_not_called()
