"""Download one SBC PDF, politely, into the local cache (ADR 0013, 0019).

The URLs come from CMS, not users, but they point at dozens of issuers'
servers, so each is checked before it is fetched and again at every redirect:
HTTPS only, and never an IP address or a local host name. A site that
refuses us — a robots.txt rule, or a 401/403 on the document itself — is
recorded as `blocked` and left alone. Nothing here tries to get past it. A
robots.txt that cannot be served is not a refusal (ADR 0020).

`revalidate` asks whether a stored document has changed, with the validators
the issuer gave us, and writes nothing.
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


NOT_MODIFIED = "not_modified"   # a revalidation only: the stored file still stands


@dataclass(frozen=True)
class FetchResult:
    status: str                 # an SbcDocument status, or NOT_MODIFIED
    path: Path | None = None    # the cached PDF, when status is "ok"
    detail: str | None = None   # why not, in a few words
    etag: str | None = None         # what the issuer gave us to ask with next time
    last_modified: str | None = None
    body: bytes | None = None       # a revalidation's bytes, not yet written anywhere
    # A failure worth trying again: a 5xx, a 429 or a network error. The
    # stored text of a document that hits one is left alone (ADR 0019).
    transient: bool = False


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
    return _fetch(url, target)


def revalidate(url: str, etag: str | None = None, last_modified: str | None = None) -> FetchResult:
    """Whether the issuer's file has changed, and its bytes if it has. Writes nothing."""
    return _fetch(url, None, (etag, last_modified))


def _fetch(url: str, target: Path | None, validators: tuple[str | None, str | None] = (None, None)) -> FetchResult:
    try:
        return _download(url, target, validators)
    except requests.RequestException as exc:
        # The type only: an exception's text can quote the URL's query string.
        logger.info("SBC fetch failed: %s", type(exc).__name__)
        return FetchResult("http_error", detail=f"network error ({type(exc).__name__})", transient=True)


def _download(url: str, target: Path | None, validators: tuple[str | None, str | None]) -> FetchResult:
    for _ in range(_MAX_REDIRECTS + 1):
        refusal = _unsafe(url) or _robots_refusal(url)
        if refusal:
            return FetchResult("blocked", detail=refusal)

        _pace(urlsplit(url).hostname)
        with requests.get(url, headers=_headers(validators), timeout=_TIMEOUT,
                          stream=True, allow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            if response.status_code == 304:
                return FetchResult(NOT_MODIFIED)
            if response.status_code in (401, 403):
                return FetchResult("blocked", detail=f"HTTP {response.status_code}")
            if response.status_code != 200:
                return FetchResult("http_error", detail=f"HTTP {response.status_code}",
                                   transient=response.status_code == 429 or response.status_code >= 500)
            return _read(response, target)
    return FetchResult("http_error", detail="too many redirects")


def _headers(validators: tuple[str | None, str | None]) -> dict[str, str]:
    """Ours, plus what the issuer gave us to ask with: a 304 costs them nothing."""
    etag, last_modified = validators
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _read(response: requests.Response, target: Path | None) -> FetchResult:
    """The response body, saved to `target`, or handed back when there is none to save to."""
    body = bytearray()
    for block in response.iter_content(_STREAM_CHUNK):
        body += block
        if len(body) > MAX_BYTES:
            return FetchResult("too_large", detail=f"over {MAX_BYTES // (1024 * 1024)} MB")
    if b"%PDF-" not in body[:_PDF_MAGIC_WINDOW]:
        return FetchResult("not_pdf", detail="response is not a PDF")

    served = {"etag": response.headers.get("ETag"), "last_modified": response.headers.get("Last-Modified")}
    if target is None:
        return FetchResult("ok", body=bytes(body), **served)
    save(bytes(body), target)
    return FetchResult("ok", target, **served)


def save(body: bytes, target: Path) -> None:
    """Write a downloaded PDF into the cache, atomically.

    Written aside and renamed into place: a killed run leaves no half file
    for the next run to trust, and a replaced file is never half-written.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".tmp")
    partial.write_bytes(body)
    partial.replace(target)


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
def _robots(origin: str) -> RobotFileParser:
    """The site's robots.txt rules, read once per run (RFC 9309 §2.3.1, ADR 0020).

    Read with our own client, not RobotFileParser.read(), for the timeout and
    User-Agent. The status decides what the site told us:

    - 2xx: these are the rules, and they are obeyed.
    - 4xx "unavailable": the file is not there to read, so no rules were
      published and the standard says a crawler may fetch. A 401 or 403 on
      `/robots.txt` says nothing about the documents themselves.
    - 5xx "unreachable": the server is failing, and the standard says assume a
      complete disallow rather than guess.

    A network error is the one place this still fails open, which RFC 9309
    would group with unreachable. It is left as it was and logged rather than
    changed unmeasured (ADR 0020).
    """
    parser = RobotFileParser()
    _pace(urlsplit(origin).hostname)
    try:
        response = requests.get(f"{origin}/robots.txt", headers={"User-Agent": USER_AGENT},
                                timeout=_TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        logger.info("robots.txt unreachable for %s (%s): proceeding", origin, type(exc).__name__)
        parser.allow_all = True
        return parser

    if response.status_code >= 500:
        parser.disallow_all = True
    elif response.status_code != 200:
        parser.allow_all = True
    else:
        parser.parse(response.text.splitlines())
    return parser


def _robots_refusal(url: str) -> str | None:
    """Why the site's robots.txt keeps us from `url`, or None."""
    parts = urlsplit(url)
    rules = _robots(f"{parts.scheme}://{parts.netloc}")
    if rules.disallow_all:
        return "robots.txt could not be served"
    return None if rules.can_fetch(USER_AGENT, url) else "robots.txt disallows it"


def _pace(host: str | None) -> None:
    wait = _last_request.get(host, 0.0) + _HOST_DELAY_SECONDS - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request[host] = time.monotonic()
