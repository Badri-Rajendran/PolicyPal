"""Fetching the California PUF from CMS: cached, atomic, and honest about "not yet"."""
from unittest.mock import Mock, patch

import pytest
import requests

from src.ingestion.ca_puf.download import NotPublishedError, download, sha256_of


def _response(status=200, content=b"PK\x03\x04zip"):
    response = Mock(status_code=status, content=content)
    response.raise_for_status.side_effect = (
        requests.HTTPError(f"{status}") if status >= 400 else None
    )
    return response


def test_a_file_is_fetched_once_and_then_kept(tmp_path):
    with patch("src.ingestion.ca_puf.download.requests.get", return_value=_response()) as get:
        first = download(2026, cache=tmp_path)
        second = download(2026, cache=tmp_path)

    assert first == second == tmp_path / "2026.zip"
    assert first.read_bytes() == b"PK\x03\x04zip"
    get.assert_called_once()
    url = get.call_args.args[0]
    assert url == "https://www.cms.gov/files/zip/californiasbpuf2026.zip"
    assert "PolicyPalRAGProject" in get.call_args.kwargs["headers"]["User-Agent"]
    assert not list(tmp_path.glob("*.tmp"))


def test_refresh_downloads_again(tmp_path):
    (tmp_path / "2026.zip").write_bytes(b"PKold")
    with patch("src.ingestion.ca_puf.download.requests.get", return_value=_response(content=b"PKnew")):
        path = download(2026, refresh=True, cache=tmp_path)

    assert path.read_bytes() == b"PKnew"


def test_a_year_cms_has_not_published_says_so_and_writes_nothing(tmp_path):
    with patch("src.ingestion.ca_puf.download.requests.get", return_value=_response(404)), \
         pytest.raises(NotPublishedError, match="2031"):
        download(2031, cache=tmp_path)

    assert not list(tmp_path.iterdir())


def test_a_server_error_or_a_web_page_is_not_kept(tmp_path):
    with patch("src.ingestion.ca_puf.download.requests.get", return_value=_response(503)), \
         pytest.raises(requests.HTTPError):
        download(2026, cache=tmp_path)
    with patch("src.ingestion.ca_puf.download.requests.get",
               return_value=_response(content=b"<html>Access denied</html>")), \
         pytest.raises(requests.RequestException, match="did not return a zip"):
        download(2026, cache=tmp_path)

    assert not list(tmp_path.iterdir())


def test_the_hash_is_of_the_bytes(tmp_path):
    path = tmp_path / "f.zip"
    path.write_bytes(b"abc")

    assert sha256_of(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
