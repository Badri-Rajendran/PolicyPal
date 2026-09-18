"""CMS Marketplace API client — the plan catalog, fetched politely.

Not a `Source`: those produce corpus chunks, and this feeds
`src/ingestion/plans.py`, which produces rows. Transport, pacing and key
redaction live in `src/core/marketplace_api.py`, shared with the chat path.
"""
import json
from dataclasses import dataclass

from src.core.logging import get_logger
from src.core.marketplace_api import REFERENCE_AGE, request

from .constants import PLANS_RAW

logger = get_logger(__name__)

# /data/county-zips is ~1.4 MB and has taken 86s to answer where it
# earlier took about one.
_BULK_REQUEST_TIMEOUT_SECONDS = 180

# Verified fixed: `limit` is ignored and every page holds 10 plans.
_PAGE_SIZE = 10

# 138 plans (14 pages) was the largest county seen. This only stops a server
# that reports a total it never reaches from paging forever.
_MAX_PAGES_PER_COUNTY = 100

# Age is the only household input that moves `premium`; income and tobacco
# move only `premium_w_credit`, which is not stored.
_REFERENCE_HOUSEHOLD = {"people": [{"age": REFERENCE_AGE}]}


@dataclass(frozen=True)
class County:
    state: str
    fips: str
    name: str
    zips: tuple[str, ...]


def county_zips(year: int) -> list[County]:
    """Every county in every state with its ZIPs, from one ~1.4 MB call.

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

    payload = request(
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


def _parse_county_zips(payload) -> list[County]:
    try:
        return [
            County(entry["state"], county["fips"], county["name"], tuple(county["zips"]))
            for entry in payload
            for county in entry["counties"]
        ]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unexpected /data/county-zips shape: {exc!r}") from None


def counties_by_state(counties: list[County]) -> dict[str, list[tuple[str, str]]]:
    """Each state's counties as `(fips, zipcode)` for `/plans/search`.

    The search wants a ZIP alongside the county. A ZIP can span counties
    (74103 is in both Tulsa and Osage), so each county carries one of its own
    ZIPs rather than resolving ZIPs to counties.

    Known limit: an issuer may serve only part of a county. Searching with one
    representative ZIP can miss such a plan; it never returns a plan that is
    not sold in the county.
    """
    by_state: dict[str, list[tuple[str, str]]] = {}
    for county in counties:
        if county.zips:
            by_state.setdefault(county.state, []).append((county.fips, county.zips[0]))
    return by_state


def county_plans(state: str, countyfips: str, zipcode: str, year: int) -> list[dict]:
    """Every plan sold in one county, across all pages.

    A failed page raises rather than returning the pages before it: a partial
    list would record the county as offering fewer plans than it does. A
    server that stops short of its own `total` is logged, not raised on.
    """
    plans: list[dict] = []
    offset = 0
    for _ in range(_MAX_PAGES_PER_COUNTY):
        payload = request(
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
