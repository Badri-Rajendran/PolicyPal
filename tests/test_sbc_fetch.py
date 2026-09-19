"""Fetching SBC PDFs: only public HTTPS hosts, never around a refusal (ADR 0013).

`requests.get` is mocked throughout; nothing here reaches the network.
"""
from unittest.mock import MagicMock

import pytest
import requests

from src.ingestion.sbc import fetch
from src.ingestion.sbc.fetch import (
    MAX_BYTES,
    NOT_MODIFIED,
    cache_path,
    fetch_pdf,
    revalidate,
)

URL = "https://sbc.example.com/plans/2026/gold.pdf"
PDF = b"%PDF-1.7\n" + b"x" * 100


def _response(status=200, body=PDF, location=None, text="", headers=None):
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.is_redirect = location is not None
    response.headers = {"Location": location} if location else dict(headers or {})
    response.text = text
    response.iter_content.return_value = [body[i:i + 64] for i in range(0, len(body), 64)]
    response.__enter__.return_value = response
    return response


@pytest.fixture(autouse=True)
def _offline(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "SBC_RAW", tmp_path)
    monkeypatch.setattr(fetch, "_pace", lambda host: None)
    fetch._robots.cache_clear()
    get = MagicMock()
    monkeypatch.setattr(fetch.requests, "get", get)
    return get


def _serve(get, pdf_response, robots=None):
    """robots.txt first (a 404 by default: no rules), then the PDF."""
    robots = robots or _response(404)
    get.side_effect = lambda url, **kw: robots if url.endswith("/robots.txt") else pdf_response


def test_a_pdf_is_cached_and_never_downloaded_twice(_offline):
    _serve(_offline, _response())

    first = fetch_pdf(URL, 2026)
    calls = _offline.call_count
    second = fetch_pdf(URL, 2026)

    assert first.status == second.status == "ok"
    assert first.path == cache_path(URL, 2026) and first.path.read_bytes() == PDF
    assert _offline.call_count == calls
    assert not first.path.with_suffix(".tmp").exists()


@pytest.mark.parametrize("url", [
    "http://sbc.example.com/gold.pdf",
    "https://10.0.0.5/gold.pdf",
    "https://[::1]/gold.pdf",
    "https://localhost/gold.pdf",
    "https://intranet/gold.pdf",
])
def test_non_https_and_non_public_hosts_are_refused_before_any_request(_offline, url):
    result = fetch_pdf(url, 2026)

    assert result.status == "blocked"
    _offline.assert_not_called()


def test_a_redirect_is_checked_again_before_it_is_followed(_offline):
    _serve(_offline, _response(302, location="http://169.254.169.254/latest/meta-data"))

    result = fetch_pdf(URL, 2026)

    assert (result.status, result.detail) == ("blocked", "not an https URL")
    assert all("169.254" not in call.args[0] for call in _offline.call_args_list)


@pytest.mark.parametrize(("status", "expected"), [(403, "blocked"), (401, "blocked"), (404, "http_error"), (503, "http_error")])
def test_http_failures_are_recorded_by_kind(_offline, status, expected):
    _serve(_offline, _response(status, body=b""))

    assert fetch_pdf(URL, 2026).status == expected


def test_robots_txt_is_honoured(_offline):
    _serve(_offline, _response(), robots=_response(200, text="User-agent: *\nDisallow: /plans/"))

    result = fetch_pdf(URL, 2026)

    assert (result.status, result.detail) == ("blocked", "robots.txt disallows it")
    assert [call.args[0] for call in _offline.call_args_list] == ["https://sbc.example.com/robots.txt"]


def test_a_site_refusing_robots_txt_is_left_alone(_offline):
    _serve(_offline, _response(), robots=_response(403))

    result = fetch_pdf(URL, 2026)

    assert (result.status, result.detail) == ("blocked", "robots.txt refused (HTTP 403)")
    assert [call.args[0] for call in _offline.call_args_list] == ["https://sbc.example.com/robots.txt"]


def test_a_body_past_the_size_cap_is_dropped_unsaved(_offline):
    _serve(_offline, _response(body=b"%PDF-" + b"x" * MAX_BYTES))

    result = fetch_pdf(URL, 2026)

    assert result.status == "too_large"
    assert not cache_path(URL, 2026).exists()


def test_an_html_page_served_as_the_pdf_is_not_saved(_offline):
    _serve(_offline, _response(body=b"<html>Access denied</html>"))

    assert fetch_pdf(URL, 2026).status == "not_pdf"
    assert not cache_path(URL, 2026).exists()


def test_a_network_error_is_a_result_naming_only_its_type(_offline):
    _offline.side_effect = requests.ConnectionError(f"failed for {URL}?token=abc")

    result = fetch_pdf(URL, 2026)

    assert (result.status, result.detail) == ("http_error", "network error (ConnectionError)")


# Asking whether a stored document has changed (ADR 0019)

_VALIDATORS = {"ETag": '"abc123"', "Last-Modified": "Wed, 10 Sep 2026 08:00:00 GMT"}


def _asked_with(get):
    """The headers of the request for the PDF itself, not robots.txt."""
    return next(call.kwargs["headers"] for call in get.call_args_list if not call.args[0].endswith("/robots.txt"))


def test_a_download_records_what_the_issuer_gave_us_to_ask_with(_offline):
    _serve(_offline, _response(headers=_VALIDATORS))

    result = fetch_pdf(URL, 2026)

    assert (result.etag, result.last_modified) == ('"abc123"', "Wed, 10 Sep 2026 08:00:00 GMT")


def test_a_revalidation_sends_them_and_reads_an_unchanged_answer(_offline):
    _serve(_offline, _response(status=304, body=b""))

    result = revalidate(URL, '"abc123"', "Wed, 10 Sep 2026 08:00:00 GMT")

    assert result.status == NOT_MODIFIED
    assert _asked_with(_offline)["If-None-Match"] == '"abc123"'
    assert _asked_with(_offline)["If-Modified-Since"] == "Wed, 10 Sep 2026 08:00:00 GMT"


def test_a_revalidation_sends_them_again_after_a_redirect(_offline):
    moved = "https://sbc.example.com/plans/2026/gold-v2.pdf"
    responses = iter([_response(status=301, location=moved), _response(status=304, body=b"")])
    _offline.side_effect = lambda url, **kw: _response(404) if url.endswith("/robots.txt") else next(responses)

    assert revalidate(URL, '"abc123"').status == NOT_MODIFIED
    assert all(call.kwargs["headers"].get("If-None-Match") == '"abc123"'
               for call in _offline.call_args_list if not call.args[0].endswith("/robots.txt"))


def test_a_changed_file_comes_back_as_bytes_and_is_not_written(_offline, tmp_path):
    _serve(_offline, _response(body=b"%PDF-1.7\nnew", headers=_VALIDATORS))

    result = revalidate(URL)

    assert (result.status, result.body) == ("ok", b"%PDF-1.7\nnew")
    assert list(tmp_path.glob("**/*.pdf")) == []


def test_a_revalidation_still_obeys_a_refusal(_offline):
    _serve(_offline, _response(), robots=_response(text="User-agent: *\nDisallow: /"))

    assert revalidate(URL, '"abc123"').status == "blocked"


@pytest.mark.parametrize(("status", "transient"), [(500, True), (503, True), (429, True), (404, False), (410, False)])
def test_only_a_server_side_failure_is_worth_trying_again(_offline, status, transient):
    """ADR 0019: a stored document keeps its text through a 5xx, not through a 404."""
    _serve(_offline, _response(status=status, body=b""))

    result = revalidate(URL)

    assert (result.status, result.transient) == ("http_error", transient)


def test_a_network_error_is_worth_trying_again(_offline):
    _offline.side_effect = requests.ConnectTimeout("connecting to sbc.example.com?plan=12345 failed")

    result = revalidate(URL)

    assert (result.status, result.transient) == ("http_error", True)
    assert "12345" not in (result.detail or "")
