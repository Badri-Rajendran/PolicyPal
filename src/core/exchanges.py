"""The exchange that sells each state's plans, and how PolicyPal prices them.

HealthCare.gov states are priced live through the CMS Marketplace API. A
filed-rate state runs its own exchange, which that API does not serve; its
plans and premiums come from CMS's state-based exchange PUF instead (ADR 0024).
A state in neither has no plan data here.
"""
from dataclasses import dataclass

from src.core.marketplace_api import MARKETPLACE_STATES


@dataclass(frozen=True)
class Exchange:
    name: str
    url: str


HEALTHCARE_GOV = Exchange("HealthCare.gov", "https://www.healthcare.gov/")

# Linked, never read: Covered California's Terms of Use forbid automated
# access (see the `coveredca` entry in src/ingestion/sources/registry.toml).
FILED_RATE_STATES: dict[str, Exchange] = {
    "CA": Exchange("Covered California", "https://www.coveredca.com/"),
}

CATALOG_STATES: tuple[str, ...] = MARKETPLACE_STATES + tuple(FILED_RATE_STATES)


def exchange_for(state: str | None) -> Exchange | None:
    if state in FILED_RATE_STATES:
        return FILED_RATE_STATES[state]
    if state in MARKETPLACE_STATES:
        return HEALTHCARE_GOV
    return None
