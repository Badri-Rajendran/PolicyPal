"""The CMS Marketplace API client.

HTTP is patched at `src.ingestion.marketplace_api.requests.request` with real
`requests.Response` objects, as in test_sources_healthcare_gov.py. No test
here reaches the network or needs a real key.
"""
import json
from unittest.mock import patch

import pytest
import requests
from pydantic import SecretStr

from src.core.exceptions import MarketplaceApiKeyMissingError
from src.ingestion import marketplace_api
from src.policypal.config import settings

KEY = "test-key-do-not-log"


@pytest.fixture(autouse=True)
def _fast_and_keyed():
    with (
        patch.object(settings, "cms_marketplace_api_key", SecretStr(KEY)),
        patch("src.ingestion.marketplace_api.time.sleep"),
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
        patch("src.ingestion.marketplace_api.requests.request", return_value=_response(500)),
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
        patch("src.ingestion.marketplace_api.requests.request", side_effect=leaky),
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
    with patch("src.ingestion.marketplace_api.requests.request", side_effect=pages) as request:
        plans = marketplace_api.county_plans("TX", "48113", "75001", 2026)

    assert [p["id"] for p in plans] == list(range(25))
    assert [call.kwargs["json"]["offset"] for call in request.call_args_list] == [0, 10, 20]


def test_a_failed_page_fails_the_whole_county():
    """A partial list would record the county as selling fewer plans than it
    does. Raising lets the orchestrator skip the county and retry it later."""
    pages = [_page(25, range(10)), _response(503)]
    with (
        patch("src.ingestion.marketplace_api.requests.request", side_effect=pages),
        pytest.raises(requests.HTTPError),
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)


@pytest.mark.parametrize("key", [None, SecretStr("")])
def test_a_missing_key_fails_before_any_request(key):
    """A blank `CMS_MARKETPLACE_API_KEY=` line is as missing as an absent one."""
    with (
        patch.object(settings, "cms_marketplace_api_key", key),
        patch("src.ingestion.marketplace_api.requests.request") as request,
        pytest.raises(MarketplaceApiKeyMissingError),
    ):
        marketplace_api.county_plans("TX", "48113", "75001", 2026)

    request.assert_not_called()
