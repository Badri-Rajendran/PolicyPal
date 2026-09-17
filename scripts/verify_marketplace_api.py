"""Verification spike for the CMS Marketplace API (Phase 1, Step 1).

docs/plans/phase-1-marketplace-api.md's Step 2 schema is designed from CMS's
published documentation, not a verified response — that is not the same
thing. This script calls the live API with a real key and prints what it
actually returns: field names, types, nullability, pagination, and rate-limit
headers, plus checks the claim that a plan catalog can be fetched per state
without a household/rate context. Its output should be pasted into that
plan doc's Step 1 by hand, then this file deleted — nothing here is imported
by the real ingestion pipeline.

Needs CMS_MARKETPLACE_API_KEY in .env (request one at
developer.cms.gov/marketplace-api/key-request.html; never commit it).

    uv run python -m scripts.verify_marketplace_api --state IL
    uv run python -m scripts.verify_marketplace_api --state IL --zipcode 60601
"""
import argparse
import json
import sys

import requests

from src.policypal.config import settings

BASE_URL = "https://marketplace.api.healthcare.gov/api/v1"
_REQUEST_TIMEOUT_SECONDS = 30
_RATE_LIMIT_HEADER_HINT = "limit"


def parse_args(args):
    parser = argparse.ArgumentParser(
        description="Probe the live CMS Marketplace API and print its actual shape."
    )
    parser.add_argument("--state", required=True, help="Two-letter state code, e.g. IL")
    parser.add_argument("--zipcode", default=None,
                        help="5-digit ZIP in --state; also exercises /plans/search")
    parser.add_argument("--year", type=int, default=2026, help="Plan year")
    return parser.parse_args(args)


def _print_response(response):
    print(f"-> {response.status_code}")
    rate_headers = {k: v for k, v in response.headers.items() if _RATE_LIMIT_HEADER_HINT in k.lower()}
    if rate_headers:
        print(f"   rate-limit headers: {rate_headers}")
    response.raise_for_status()


def _get(path, apikey, **params):
    print(f"GET {path} params={params}")
    response = requests.get(
        f"{BASE_URL}{path}", params={**params, "apikey": apikey}, timeout=_REQUEST_TIMEOUT_SECONDS
    )
    _print_response(response)
    return response.json()


def _post(path, apikey, body):
    print(f"POST {path}")
    response = requests.post(
        f"{BASE_URL}{path}", params={"apikey": apikey}, json=body, timeout=_REQUEST_TIMEOUT_SECONDS
    )
    _print_response(response)
    return response.json()


def main(args=sys.argv[1:]):
    parsed = parse_args(args)

    if settings.cms_marketplace_api_key is None:
        print("Set CMS_MARKETPLACE_API_KEY in .env first (never commit it) — "
              "request one at developer.cms.gov/marketplace-api/key-request.html")
        return 1

    apikey = settings.cms_marketplace_api_key.get_secret_value()

    print("=== /issuers — documented as state-only, no household context ===")
    issuers = _get("/issuers", apikey, year=parsed.year, state=parsed.state)
    print(json.dumps(issuers, indent=2)[:2000])

    if parsed.zipcode:
        print("\n=== /plans/search — documented as requiring household + place + market ===")
        body = {
            "household": {
                "income": 0,
                "people": [{"age": 30, "aptc_eligible": False, "gender": "Male", "uses_tobacco": False}],
            },
            "market": "Individual",
            "place": {"state": parsed.state, "zipcode": parsed.zipcode, "countyfips": None},
            "year": parsed.year,
        }
        search = _post("/plans/search", apikey, body)
        plans = search.get("plans", [])
        print(f"total={search.get('total')}, returned={len(plans)}")
        print(json.dumps(plans[:1], indent=2)[:2000])

        if plans:
            plan_id = plans[0]["id"]
            print(f"\n=== /plans/{plan_id} — documented as NOT requiring household context ===")
            detail = _get(f"/plans/{plan_id}", apikey, year=parsed.year)
            print(json.dumps(detail, indent=2)[:3000])

    return 0


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    sys.exit(main())
