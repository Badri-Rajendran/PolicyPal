"""Fetch the California PUF from CMS, once per plan year, into data/plans/raw/ca_puf/."""
import hashlib
from pathlib import Path

import requests

from ..constants import PLANS_RAW, USER_AGENT

PUF_URL = "https://www.cms.gov/files/zip/californiasbpuf{year}.zip"
CACHE = PLANS_RAW / "ca_puf"
_TIMEOUT = (10, 120)  # connect, read: the 2026 file is about 1 MB


class NotPublishedError(Exception):
    """CMS has not published this year's file; it does so May to August of the plan year."""


def download(year: int, *, refresh: bool = False, cache: Path = CACHE) -> Path:
    path = cache / f"{year}.zip"
    if path.exists() and not refresh:
        return path
    url = PUF_URL.format(year=year)
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT)
    if response.status_code == 404:
        raise NotPublishedError(f"CMS has not published the {year} California PUF yet ({url})")
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise requests.RequestException(f"{url} did not return a zip")
    cache.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed: a killed run leaves the old file or none.
    partial = path.with_suffix(".tmp")
    partial.write_bytes(response.content)
    partial.replace(path)
    return path


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
