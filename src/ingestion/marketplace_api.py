"""CMS Marketplace API client — the plan catalog, fetched politely.

Not a `Source`: those produce corpus chunks, and this feeds
`src/ingestion/plans.py`, which produces rows. What each endpoint verifiably
returns is recorded in docs/findings/cms-marketplace-api.md.
"""
import json
import time

import requests

from src.core.exceptions import MarketplaceApiKeyMissingError
from src.core.logging import get_logger
from src.policypal.config import settings

from .constants import MARKETPLACE_API_BASE_URL, PLANS_RAW

logger = get_logger(__name__)

_REQUEST_TIMEOUT_SECONDS = 60

# /data/county-zips is ~1.4 MB and has taken 86s to answer where it
# earlier took about one.
_BULK_REQUEST_TIMEOUT_SECONDS = 180

# Verified fixed: `limit` is ignored and every page holds 10 plans.
_PAGE_SIZE = 10

# A free public API. With request latency this lands near a quarter of the
# verified 1000/min limit — polite, and robust if CMS tightens it.
_REQUEST_DELAY_SECONDS = 0.2

# 138 plans (14 pages) was the largest county seen. This only stops a server
# that reports a total it never reaches from paging forever.
_MAX_PAGES_PER_COUNTY = 100

# CMS's own convention for comparing premiums. Age is the only household
# input that moves `premium`; income and tobacco move only `premium_w_credit`,
# which is not stored. Omitting the household does not mean age 27 — CMS
# applies its own undocumented default — so this is sent on every call, and
# is a constant rather than a setting because it defines what the stored
# premium means.
REFERENCE_AGE = 27
_REFERENCE_HOUSEHOLD = {"people": [{"age": REFERENCE_AGE}]}


def _api_key() -> str:
    # A blank `CMS_MARKETPLACE_API_KEY=` line yields an empty SecretStr, not
    # None — it is just as missing.
    key = settings.cms_marketplace_api_key
    if key is None or not key.get_secret_value():
        raise MarketplaceApiKeyMissingError(
            "CMS_MARKETPLACE_API_KEY is not set. Request a key at "
            "https://developer.cms.gov/marketplace-api and add it to .env."
        )
    return key.get_secret_value()


def _request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: int = _REQUEST_TIMEOUT_SECONDS,
):
    """One paced call. The key is a query parameter, so no error may carry the URL.

    `requests` embeds the full URL — query string and key — both in
    `raise_for_status()` errors and in connection and timeout errors, and the
    caller logs error text. Every failure is re-raised with method and path only.
    """
    time.sleep(_REQUEST_DELAY_SECONDS)
    try:
        response = requests.request(
            method,
            f"{MARKETPLACE_API_BASE_URL}{path}",
            params={**(params or {}), "apikey": _api_key()},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise requests.RequestException(f"{method} {path} failed: {type(exc).__name__}") from None

    if not response.ok:
        raise requests.HTTPError(f"{method} {path} returned {response.status_code}")
    return response.json()


def counties_by_state(year: int) -> dict[str, list[tuple[str, str]]]:
    """Each state's counties as `(fips, zipcode)`, from one ~1.4 MB call.

    `/plans/search` wants a ZIP alongside the county. A ZIP can span counties
    (74103 is in both Tulsa and Osage), so each county carries one of its own
    ZIPs rather than resolving ZIPs to counties.

    Known limit: an issuer may serve only part of a county. Searching with one
    representative ZIP can miss such a plan; it never returns a plan that is
    not sold in the county.

    Cached per plan year under `data/plans/raw/`: the crosswalk is fixed for a
    year, and runs go one state at a time. Delete the file to refresh it.
    """
    cache = PLANS_RAW / f"county_zips_{year}.json"
    if cache.exists():
        try:
            return _parse_county_zips(json.loads(cache.read_text(encoding="utf-8")))
        except ValueError:
            # Unreadable cache means refetch, not a run that fails forever
            # until someone finds and deletes the file.
            logger.warning("county-zips cache %s is unreadable; refetching", cache)

    payload = _request(
        "GET", "/data/county-zips", params={"year": year}, timeout=_BULK_REQUEST_TIMEOUT_SECONDS
    )
    # Parsed before writing, so a malformed response never becomes the cache.
    counties = _parse_county_zips(payload)
    cache.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed into place: a run killed mid-write leaves the
    # old file or none, never a truncated one.
    partial = cache.with_suffix(".tmp")
    partial.write_text(json.dumps(payload), encoding="utf-8")
    partial.replace(cache)
    return counties


def _parse_county_zips(payload) -> dict[str, list[tuple[str, str]]]:
    try:
        return {
            entry["state"]: [
                (county["fips"], county["zips"][0]) for county in entry["counties"] if county.get("zips")
            ]
            for entry in payload
        }
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"unexpected /data/county-zips shape: {exc!r}") from None


def county_plans(state: str, countyfips: str, zipcode: str, year: int) -> list[dict]:
    """Every plan sold in one county, across all pages.

    A failed page raises rather than returning the pages before it: a partial
    list would record the county as offering fewer plans than it does. A
    server that stops short of its own `total` is logged, not raised on.
    """
    plans: list[dict] = []
    offset = 0
    for _ in range(_MAX_PAGES_PER_COUNTY):
        payload = _request(
            "POST",
            "/plans/search",
            body={
                "household": _REFERENCE_HOUSEHOLD,
                "market": "Individual",
                "place": {"state": state, "countyfips": countyfips, "zipcode": zipcode},
                "year": year,
                "offset": offset,
            },
        )
        if not isinstance(payload, dict) or "plans" not in payload or "total" not in payload:
            raise ValueError("/plans/search response has no 'plans' or 'total'")

        page = payload["plans"]
        plans.extend(page)
        offset += _PAGE_SIZE
        if offset >= payload["total"]:
            return plans
        if not page:
            logger.warning("county %s: empty page at %d of %d plans", countyfips, len(plans), payload["total"])
            return plans

    logger.warning("stopped paging county %s at %d pages", countyfips, _MAX_PAGES_PER_COUNTY)
    return plans
