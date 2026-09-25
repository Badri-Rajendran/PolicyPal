"""California's geographic rating areas, transcribed from CMS.

Source: https://www.cms.gov/cciio/programs-and-initiatives/health-insurance-market-reforms/ca-gra
Verified 2026-09-24 against the raw page, and against the 2026 PUF: every
plan's rated areas are areas where it is sold. Re-check yearly
(docs/runbooks/california.md).

Counties map to one area, except Los Angeles, which CMS splits by 3-digit ZIP
prefix. Some real Los Angeles ZIPs have a prefix in neither list (901 and 930
in CMS's 2026 crosswalk): they have no area, and their plans are shown
unpriced, never at a guessed price.
"""
from collections.abc import Iterable

LOS_ANGELES = "06037"

_AREAS: dict[int, tuple[str, ...]] = {
    # Alpine, Del Norte, Siskiyou, Modoc, Lassen, Shasta, Trinity, Humboldt, Tehama, Plumas, Nevada,
    # Sierra, Mendocino, Lake, Butte, Glenn, Sutter, Yuba, Colusa, Amador, Calaveras, Tuolumne
    1: ("06003", "06015", "06093", "06049", "06035", "06089", "06105", "06023", "06103", "06063", "06057",
        "06091", "06045", "06033", "06007", "06021", "06101", "06115", "06011", "06005", "06009", "06109"),
    2: ("06055", "06097", "06095", "06041"),  # Napa, Sonoma, Solano, Marin
    3: ("06067", "06061", "06017", "06113"),  # Sacramento, Placer, El Dorado, Yolo
    4: ("06075",),  # San Francisco
    5: ("06013",),  # Contra Costa
    6: ("06001",),  # Alameda
    7: ("06085",),  # Santa Clara
    8: ("06081",),  # San Mateo
    9: ("06087", "06053", "06069"),  # Santa Cruz, Monterey, San Benito
    10: ("06077", "06099", "06047", "06043", "06107"),  # San Joaquin, Stanislaus, Merced, Mariposa, Tulare
    11: ("06039", "06019", "06031"),  # Madera, Fresno, Kings
    12: ("06079", "06083", "06111"),  # San Luis Obispo, Santa Barbara, Ventura
    13: ("06051", "06027", "06025"),  # Mono, Inyo, Imperial
    14: ("06029",),  # Kern
    17: ("06071", "06065"),  # San Bernardino, Riverside
    18: ("06059",),  # Orange
    19: ("06073",),  # San Diego
}

COUNTY_AREAS: dict[str, int] = {fips: area for area, counties in _AREAS.items() for fips in counties}

# Los Angeles County only; a prefix is read only for a ZIP in that county.
LA_ZIP3_AREAS: dict[str, int] = {
    **dict.fromkeys(("906", "907", "908", "910", "911", "912", "915", "917", "918", "935"), 15),
    **dict.fromkeys(("900", "902", "903", "904", "905", "913", "914", "916", "923", "928", "932"), 16),
}


class UnmappedCountyError(ValueError):
    """A California county the transcribed map does not have: fix the map, never guess."""


def county_area(countyfips: str) -> int:
    try:
        return COUNTY_AREAS[countyfips]
    except KeyError:
        raise UnmappedCountyError(f"county {countyfips} is not in the California rating-area map") from None


def area_for(countyfips: str, zipcode: str) -> int | None:
    """The rating area a ZIP in a county prices in; None for an unlisted Los Angeles prefix."""
    if countyfips == LOS_ANGELES:
        return LA_ZIP3_AREAS.get(zipcode[:3])
    return county_area(countyfips)


def table_rows(countyfips: Iterable[str]) -> list[tuple[str, str, int]]:
    """`(countyfips, zip3, area)` rows for `rating_areas`; zip3 '' means the whole county."""
    rows: list[tuple[str, str, int]] = []
    for fips in sorted(set(countyfips)):
        if fips == LOS_ANGELES:
            rows += [(fips, zip3, area) for zip3, area in sorted(LA_ZIP3_AREAS.items())]
        else:
            rows.append((fips, "", county_area(fips)))
    return rows
