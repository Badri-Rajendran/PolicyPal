"""The hand-curated California data: rating areas and issuer names (ADR 0024)."""
import pytest

from src.ingestion.ca_puf.issuers import CA_ISSUERS, UnknownIssuerError, issuer_name
from src.ingestion.ca_puf.rating_areas import (
    COUNTY_AREAS,
    LA_ZIP3_AREAS,
    LOS_ANGELES,
    UnmappedCountyError,
    area_for,
    county_area,
    table_rows,
)


def test_every_california_county_but_los_angeles_has_one_area():
    assert len(COUNTY_AREAS) == 57
    assert LOS_ANGELES not in COUNTY_AREAS
    assert all(fips.startswith("06") and len(fips) == 5 for fips in COUNTY_AREAS)
    # Areas 15 and 16 are Los Angeles's alone.
    assert set(COUNTY_AREAS.values()) == set(range(1, 15)) | {17, 18, 19}


@pytest.mark.parametrize("fips, area", [
    ("06003", 1), ("06041", 2), ("06067", 3), ("06075", 4), ("06013", 5), ("06001", 6),
    ("06085", 7), ("06081", 8), ("06053", 9), ("06107", 10), ("06019", 11), ("06111", 12),
    ("06025", 13), ("06029", 14), ("06065", 17), ("06059", 18), ("06073", 19),
])
def test_counties_are_in_cmss_areas(fips, area):
    assert county_area(fips) == area


def test_los_angeles_splits_by_zip_prefix_and_an_unlisted_prefix_has_no_area():
    assert area_for(LOS_ANGELES, "90601") == 15
    assert area_for(LOS_ANGELES, "90012") == 16
    assert area_for(LOS_ANGELES, "93550") == 15
    assert area_for(LOS_ANGELES, "93243") == 16
    # Real Los Angeles ZIPs whose prefix CMS lists in neither area: never guessed.
    for zipcode in ("90134", "90140", "90189", "93063", "90901"):
        assert area_for(LOS_ANGELES, zipcode) is None
    assert len(LA_ZIP3_AREAS) == 21
    # A prefix is read only in Los Angeles: elsewhere the county decides.
    assert area_for("06059", "90601") == 18


def test_a_county_missing_from_the_map_is_an_error_not_a_guess():
    with pytest.raises(UnmappedCountyError):
        county_area("06999")
    with pytest.raises(UnmappedCountyError):
        area_for("06999", "99999")


def test_table_rows_are_whole_county_rows_and_los_angeles_prefix_rows():
    rows = table_rows(["06059", LOS_ANGELES, "06059"])

    assert ("06059", "", 18) in rows
    assert ("06037", "900", 16) in rows and ("06037", "935", 15) in rows
    assert not any(fips == LOS_ANGELES and zip3 == "" for fips, zip3, _ in rows)
    assert len(rows) == 1 + 21
    with pytest.raises(UnmappedCountyError):
        table_rows(["06999"])


def test_the_eleven_2026_issuers_are_named_and_an_unknown_one_is_refused():
    assert len(CA_ISSUERS) == 11
    assert issuer_name("40513") == "Kaiser Permanente"
    assert issuer_name("70285") == "Blue Shield of California"
    assert issuer_name("93689") == "Western Health Advantage"
    with pytest.raises(UnknownIssuerError, match="12345"):
        issuer_name("12345")
