"""Which exchange sells a state's plans, and which plan year is on sale (ADR 0024)."""
from datetime import date

import pytest

from src.core.exchanges import (
    CATALOG_STATES,
    FILED_RATE_STATES,
    HEALTHCARE_GOV,
    exchange_for,
)
from src.core.marketplace_api import MARKETPLACE_STATES
from src.core.plan_year import plan_year_on_sale


def test_each_state_is_sent_to_the_exchange_that_sells_its_plans():
    assert exchange_for("TX") == HEALTHCARE_GOV
    assert exchange_for("CA").name == "Covered California"
    assert exchange_for("CA").url == "https://www.coveredca.com/"
    # A state running its own exchange that PolicyPal has no data for: no name to give.
    assert exchange_for("NY") is None
    assert exchange_for(None) is None


def test_the_catalog_states_are_the_api_states_plus_the_filed_rate_ones():
    assert set(CATALOG_STATES) == set(MARKETPLACE_STATES) | {"CA"}
    assert not set(FILED_RATE_STATES) & set(MARKETPLACE_STATES)
    # California must never join the API's list: the API does not serve it.
    assert len(MARKETPLACE_STATES) == 30
    assert "CA" not in MARKETPLACE_STATES


@pytest.mark.parametrize("on, year", [
    (date(2026, 1, 1), 2026),
    (date(2026, 10, 31), 2026),
    (date(2026, 11, 1), 2027),
    (date(2026, 12, 31), 2027),
    (date(2027, 1, 31), 2027),
])
def test_next_years_plans_go_on_sale_on_november_1(on, year):
    assert plan_year_on_sale(on) == year
