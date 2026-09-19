"""Download one SBC PDF, politely, into the local cache (ADR 0013).

The URLs come from CMS, not users, but they point at dozens of issuers'
servers, so each is checked before it is fetched and again at every redirect:
HTTPS only, and never an IP address or a local host name. A site that
refuses us — robots.txt, or a 401/403 — is recorded as `blocked` and left
alone. Nothing here tries to get past it.
"""
import hashlib
import ipaddress
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from src.core.logging import get_logger

from ..constants import SBC_RAW, USER_AGENT

logger = get_logger(__name__)

MAX_BYTES = 15 * 1024 * 1024        # an SBC is under 3 MB; far larger is not one
_TIMEOUT = (10, 60)                 # (connect, read) seconds
_HOST_DELAY_SECONDS = 2.0           # between two requests to the same host
_MAX_REDIRECTS = 5
_STREAM_CHUNK = 64 * 1024
# A PDF may carry a few bytes of junk before its header; readers look this far.
_PDF_MAGIC_WINDOW = 1024

_last_request: dict[str, float] = {}


@dataclass(frozen=True)
class FetchResult:
    status: str                 # an SbcDocument status
    path: Path | None = None    # the cached PDF, when status is "ok"
    detail: str | None = None   # why not, in a few words


def url_key(url: str) -> str:
    """A short, stable, filesystem-safe name for a URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def cache_path(url: str, year: int) -> Path:
    return SBC_RAW / str(year) / f"{url_key(url)}.pdf"


def fetch_pdf(url: str, year: int) -> FetchResult:
    """The SBC at `url`, from the cache or the network. Never raises for a bad fetch."""
    target = cache_path(url, year)
    if target.exists():
        return FetchResult("ok", target)

    try:
        return _download(url, target)
    except requests.RequestException as exc:
        # The type only: an exception's text can quote the URL's query string.
        logger.info("SBC fetch failed: %s", type(exc).__name__)
        return FetchResult("http_error", detail=f"network error ({type(exc).__name__})")


def _download(url: str, target: Path) -> FetchResult:
    for _ in range(_MAX_REDIRECTS + 1):
        refusal = _unsafe(url)
        if refusal:
            return FetchResult("blocked", detail=refusal)
        refusal = _robots_refusal(url)
        if refusal:
            return FetchResult("blocked", detail=refusal)

        _pace(urlsplit(url).hostname)
        with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT,
                          stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            if response.status_code in (401, 403):
                return FetchResult("blocked", detail=f"HTTP {response.status_code}")
            if response.status_code != 200:
                return FetchResult("http_error", detail=f"HTTP {response.status_code}")
            return _save(response, target)
    return FetchResult("http_error", detail="too many redirects")


def _save(response: requests.Response, target: Path) -> FetchResult:
    body = bytearray()
    for block in response.iter_content(_STREAM_CHUNK):
        body += block
        if len(body) > MAX_BYTES:
            return FetchResult("too_large", detail=f"over {MAX_BYTES // (1024 * 1024)} MB")
    if b"%PDF-" not in body[:_PDF_MAGIC_WINDOW]:
        return FetchResult("not_pdf", detail="response is not a PDF")

    target.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed into place: a killed run leaves no half file
    # for the next run to trust.
    partial = target.with_suffix(".tmp")
    partial.write_bytes(body)
    partial.replace(target)
    return FetchResult("ok", target)


def _unsafe(url: str) -> str | None:
    """Why `url` must not be fetched, or None."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https":
        return "not an https URL"
    if not host or "." not in host or host == "localhost" or host.endswith((".local", ".internal")):
        return "not a public host name"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return "an IP address, not a host name"


@lru_cache(maxsize=256)
def _robots(origin: str) -> RobotFileParser | int:
    """The site's robots.txt rules, read once per run, or the 401/403 it answered with.

    Read with our own client, not RobotFileParser.read(), for the timeout and
    User-Agent. As robots.txt conventions go: 401/403 means stay out, any
    other failure means no rules were published.
    """
    parser = RobotFileParser()
    _pace(urlsplit(origin).hostname)
    try:
        response = requests.get(f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT},
                                timeout=_TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        parser.allow_all = True
        return parser
    if response.status_code in (401, 403):
        return response.status_code
    if response.status_code != 200:
        parser.allow_all = True
    else:
        parser.parse(response.text.splitlines())
    return parser


def _robots_refusal(url: str) -> str | None:
    """Why the site's robots.txt keeps us from `url`, or None."""
    parts = urlsplit(url)
    rules = _robots(f"{parts.scheme}://{parts.netloc}")
    if isinstance(rules, int):
        return f"robots.txt refused (HTTP {rules})"
    return None if rules.can_fetch(USER_AGENT, url) else "robots.txt disallows it"


def _pace(host: str | None) -> None:
    wait = _last_request.get(host, 0.0) + _HOST_DELAY_SECONDS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()
