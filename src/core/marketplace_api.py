"""CMS Marketplace API transport, shared by plan ingestion and the chat path.

In core because both `src/ingestion/` and `src/services/` call it, and
services must not import from ingestion (ADR 0005). What each endpoint
verifiably returns is recorded in docs/findings/cms-marketplace-api.md.
"""
import time
from decimal import Decimal

import requests

from src.core.exceptions import MarketplaceApiKeyMissingError
from src.policypal.config import settings

MARKETPLACE_API_BASE_URL = "https://marketplace.api.healthcare.gov/api/v1"

# The states this API serves: marketplace_model FFM (27) plus SupportedSBM
# (AR, OK, OR), per GET /states for plan year 2026. The other 21 states and
# DC run their own exchanges, and the API rejects them ("state is not a
# valid marketplace state"), so failing locally is kinder.
MARKETPLACE_STATES = (
    "AK", "AL", "AR", "AZ", "DE", "FL", "HI", "IA", "IN", "KS",
    "LA", "MI", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "OH",
    "OK", "OR", "SC", "SD", "TN", "TX", "UT", "WI", "WV", "WY",
)

# CMS's own convention for comparing premiums, and what the stored
# `premium_reference` means. Omitting the household does not mean age 27 —
# CMS applies its own undocumented default — so it is always sent.
REFERENCE_AGE = 27

# POST /plans verifiably prices 30 IDs in one call, in the order requested.
MAX_PREMIUM_BATCH = 30

REQUEST_TIMEOUT_SECONDS = 60

# A free public API. With request latency this lands near a quarter of the
# verified 1000/min limit — polite, and robust if CMS tightens it.
_REQUEST_DELAY_SECONDS = 0.2


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


def request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
):
    """One paced call. The key is a query parameter, so no error may carry the URL.

    `requests` embeds the full URL — query string and key — both in
    `raise_for_status()` errors and in connection and timeout errors, and
    callers log error text. Every failure is re-raised with method and path only.
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


def age_rated_premiums(
    plan_ids: list[str], *, age: int, state: str, countyfips: str, zipcode: str, year: int
) -> dict[str, Decimal]:
    """Unsubsidized monthly premiums for one person of `age`, by plan ID.

    A plan CMS does not price in that county comes back with a premium of 0,
    not an error, so only positive premiums are kept: a missing ID means
    "no live price", never "free". Raises on any transport or shape failure.
    """
    if state not in MARKETPLACE_STATES:
        # A filed-rate state is priced from plan_rates (ADR 0024); asking CMS
        # would spend a request on a state the API does not serve.
        raise ValueError(f"{state} is not served by the Marketplace API")
    payload = request(
        "POST",
        "/plans",
        body={
            "plan_ids": plan_ids,
            "household": {"people": [{"age": age}]},
            "place": {"state": state, "countyfips": countyfips, "zipcode": zipcode},
            "market": "Individual",
            "year": year,
        },
        timeout=settings.cms_live_timeout_seconds,
    )
    # ValueError, not TypeError: callers treat it as "CMS sent something unusable".
    if not isinstance(payload, dict) or not isinstance(payload.get("plans"), list):
        raise ValueError("/plans response has no 'plans' list")  # noqa: TRY004

    requested = set(plan_ids)
    premiums = {}
    for plan in payload["plans"]:
        if not isinstance(plan, dict) or plan.get("id") not in requested:
            continue
        premium = plan.get("premium")
        # bool is an int subclass; `True` is not a price.
        if isinstance(premium, int | float) and not isinstance(premium, bool) and premium > 0:
            premiums[plan["id"]] = Decimal(str(premium)).quantize(Decimal("0.01"))
    return premiums
