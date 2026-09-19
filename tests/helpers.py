"""Shared by the API tests: every signup needs a valid profile (ADR 0012)."""
from src.models.plan import ZipCounty

# Seeded into each `client` transaction by conftest; plan year 1999 and ZIP
# codes 0000x keep them apart from a locally ingested crosswalk.
SEED_YEAR = 1999
ZIP_COUNTIES = (
    ("00001", "99001", "Alpha", "TX"),
    ("00002", "99001", "Alpha", "TX"),
    ("00002", "99002", "Beta", "TX"),
    ("00009", "99003", "Gamma", "IL"),
)

PROFILE = {"zip_code": "00001", "date_of_birth": "1990-05-17"}


def seed_zip_counties(session) -> None:
    session.add_all(
        ZipCounty(zipcode=zipcode, plan_year=SEED_YEAR, countyfips=fips, county_name=name, state=state)
        for zipcode, fips, name, state in ZIP_COUNTIES
    )
    session.flush()
