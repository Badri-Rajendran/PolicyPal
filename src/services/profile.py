"""The plan-search profile: ZIP code, date of birth and county (ADR 0012).

Personal data. Nothing here logs a value, and nothing here is sent to the
LLM: chat fills the profile into a plan search on the server side.
"""
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from src.core.marketplace_api import MARKETPLACE_STATES
from src.models.plan import ZipCounty

from .plan_search import CountyOption

# For annotations only. Importing the model at runtime pulls `User` into the
# mapper registry without the `Thread` its relationship names, and the first
# query then fails in any process that never imports the chat models — the
# eval and scripts/ask.py, which reach this module through the plan tool.
if TYPE_CHECKING:
    from src.models.user import User

# COPPA's line. Nobody younger may hold an account, and nothing about them is
# stored: the check runs before any row is written.
MIN_SIGNUP_AGE = 13
_MAX_AGE = 120

# "Today" where it is earliest on Earth (UTC-12). Someone old enough on that
# date is old enough in every US time zone; a UTC date would admit a
# 12-year-old in Hawaii for up to eleven hours.
_EARLIEST_ZONE = timezone(-timedelta(hours=12))


def today() -> date:
    return datetime.now(UTC).astimezone(_EARLIEST_ZONE).date()


def age_on(date_of_birth: date, on: date) -> int:
    """Whole years, turning over on the birthday itself."""
    return on.year - date_of_birth.year - ((on.month, on.day) < (date_of_birth.month, date_of_birth.day))


class ProfileInvalidError(Exception):
    """A profile that fails a rule. Carries field names and messages, never values."""

    def __init__(self, errors: list[dict]):
        self.errors = errors


@dataclass(frozen=True)
class PlanProfile:
    """What a plan search needs from the profile, filled in server-side."""

    zip_code: str
    age: int
    county_fips: str


def counties_for_zip(session, zip_code: str) -> list[CountyOption]:
    """The ZIP's counties in the latest crosswalk year, in any state."""
    year = session.scalar(select(func.max(ZipCounty.plan_year)).where(ZipCounty.zipcode == zip_code))
    if year is None:
        return []
    rows = session.execute(
        select(ZipCounty.countyfips, ZipCounty.county_name, ZipCounty.state)
        .where(ZipCounty.zipcode == zip_code, ZipCounty.plan_year == year)
        .order_by(ZipCounty.countyfips)
    ).all()
    return [CountyOption(*row) for row in rows]


def is_marketplace_state(state: str | None) -> bool:
    return state in MARKETPLACE_STATES


def validate_profile(session, *, zip_code: str, date_of_birth: date, county_fips: str | None) -> CountyOption:
    """The county the profile resolves to, or ProfileInvalidError with every problem found.

    The age check comes first and needs no database, so a date of birth
    under the minimum is refused before anything is looked up or written.
    """
    errors = []
    on = today()
    if date_of_birth > on:
        errors.append({"field": "date_of_birth", "message": "Date of birth can't be in the future."})
    elif age_on(date_of_birth, on) < MIN_SIGNUP_AGE:
        errors.append({"field": "date_of_birth", "message": f"You must be at least {MIN_SIGNUP_AGE} to use PolicyPal."})
    elif age_on(date_of_birth, on) > _MAX_AGE:
        errors.append({"field": "date_of_birth", "message": "Enter a real date of birth."})

    counties = counties_for_zip(session, zip_code)
    county = None
    if not counties:
        errors.append({"field": "zip_code", "message": "We don't recognise this ZIP code."})
    elif len(counties) == 1:
        county = counties[0]
    else:
        county = next((c for c in counties if c.fips == county_fips), None)
        if county is None:
            message = "Choose your county." if county_fips is None else "Choose a county in this ZIP code."
            errors.append({"field": "county_fips", "message": message})

    if errors:
        raise ProfileInvalidError(errors)
    return county


def apply_profile(user: "User", *, zip_code: str, date_of_birth: date, county: CountyOption) -> None:
    user.zip_code = zip_code
    user.date_of_birth = date_of_birth
    user.county_fips = county.fips
    user.county_name = county.name
    user.state = county.state


def plan_profile(user: "User") -> PlanProfile | None:
    """The user's search defaults, or None for an account without a complete profile."""
    if not user.profile_complete:
        return None
    return PlanProfile(user.zip_code, age_on(user.date_of_birth, today()), user.county_fips)
