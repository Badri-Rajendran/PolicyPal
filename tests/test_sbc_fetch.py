"""Fetching SBC PDFs: only public HTTPS hosts, never around a refusal (ADR 0013).

`requests.get` is mocked throughout; nothing here reaches the network.
"""
from unittest.mock import MagicMock

import pytest
import requests

from src.ingestion.sbc import fetch
from src.ingestion.sbc.fetch import MAX_BYTES, cache_path, fetch_pdf

URL = "https://sbc.example.com/plans/2026/gold.pdf"
PDF = b"%PDF-1.7\n" + b"x" * 100


def _response(status=200, body=PDF, location=None, text=""):
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.is_redirect = location is not None
    response.headers = {"Location": location} if location else {}
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
