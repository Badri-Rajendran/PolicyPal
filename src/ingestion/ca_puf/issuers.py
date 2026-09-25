"""Names of California's 2026 Covered California issuers, by HIOS issuer ID.

The PUF's ISSUER NAME column is blank on every row, so these are curated:
- the 11 carriers in Covered California's 2026 rates announcement (news
  release, 2025-08-14);
- matched to IDs by each issuer's network names and service-area footprint in
  the 2026 PUF (e.g. 84014 sells only in Santa Clara, Valley Health Plan's
  county; 47579 only in San Francisco and San Mateo, CCHP's).

Verified 2026-09-24. Re-check before each year's load (docs/runbooks/california.md).
"""

CA_ISSUERS: dict[str, str] = {
    "18126": "Molina Healthcare",
    "27603": "Anthem Blue Cross",
    "40513": "Kaiser Permanente",
    "47579": "Balance by CCHP",
    "51396": "Inland Empire Health Plan",
    "67138": "Health Net",
    "70285": "Blue Shield of California",
    "84014": "Valley Health Plan",
    "92499": "Sharp Health Plan",
    "92815": "L.A. Care Health Plan",
    "93689": "Western Health Advantage",
}


class UnknownIssuerError(ValueError):
    """An issuer the curated list does not name: add it, with its source, rather than guess."""


def issuer_name(hios_issuer_id: str) -> str:
    try:
        return CA_ISSUERS[hios_issuer_id]
    except KeyError:
        raise UnknownIssuerError(f"issuer {hios_issuer_id} is not in CA_ISSUERS") from None
