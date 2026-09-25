"""`make ingest-ca-plans YEAR=2026 [ZIP=path] [REFRESH=1]`: load California's plans from the CMS PUF.

    uv run python -m src.ingestion.ca_puf --year 2026
"""
import argparse
import sys
from pathlib import Path

import requests
from sqlalchemy import exists, select

from src.core.db import get_session
from src.core.exceptions import MarketplaceApiKeyMissingError
from src.core.logging import get_logger
from src.models.plan import ZipCounty

from ..marketplace_api import county_zips
from ..plans import _write_zip_counties
from ..sources.registry import SourceNotApprovedError, require_enabled
from .download import PUF_URL, NotPublishedError, download, sha256_of
from .load import STATE, LoadError, load
from .read import PufFormatError, read_puf

logger = get_logger(__name__)

# Exit status for "CMS has not published this year's file yet": not an error,
# so a scheduled run can tell it apart from a failure.
NOT_PUBLISHED = 3


def parse_args(args):
    parser = argparse.ArgumentParser(description="Load California's Covered California plans from the CMS PUF.")
    parser.add_argument("--year", type=int, required=True, help="Plan year, e.g. 2026")
    parser.add_argument("--zip", help="A PUF zip downloaded by hand, instead of fetching it")
    parser.add_argument("--refresh", action="store_true", help="Download again even if a copy is kept")
    return parser.parse_args(args)


def _ensure_crosswalk(year: int) -> None:
    """California's ZIP-to-county rows for the year, from CMS, if not already stored."""
    with get_session() as session:
        if session.scalar(select(exists().where(ZipCounty.state == STATE, ZipCounty.plan_year == year))):
            return
    print(f"No ZIP-to-county crosswalk for {year}; fetching CMS's (needs CMS_MARKETPLACE_API_KEY).")
    crosswalk = county_zips(year)
    with get_session() as session:
        print(f"{_write_zip_counties(session, crosswalk, year)} ZIP-to-county pairs recorded for {year}")


def main(args=sys.argv[1:]):
    parsed = parse_args(args)
    try:
        require_enabled("cms_ca_sbe_puf")
        path = Path(parsed.zip) if parsed.zip else download(parsed.year, refresh=parsed.refresh)
        puf = read_puf(path, parsed.year)
        _ensure_crosswalk(parsed.year)
        file_url = f"file:{path.name}" if parsed.zip else PUF_URL.format(year=parsed.year)
        with get_session() as session:
            report = load(session, puf, year=parsed.year, file_url=file_url, sha256=sha256_of(path))
    except NotPublishedError as exc:
        print(exc)
        sys.exit(NOT_PUBLISHED)
    except (SourceNotApprovedError, PufFormatError, LoadError, MarketplaceApiKeyMissingError,
            requests.RequestException, OSError) as exc:
        sys.exit(f"California plans not loaded: {exc}")

    print(f"{report.plans} plans from {report.issuers} issuers, file {puf.label}: {report.plan_counties} "
          f"plan-county rows ({report.dropped_unrated} dropped: no rate there), {report.rates} rates")
    if report.unrated_zips:
        print(f"Los Angeles ZIPs with no CMS rating area, shown unpriced: {', '.join(report.unrated_zips)}")
    logger.info("california plans loaded: %d plans, %d rates, file %s", report.plans, report.rates, puf.label)


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    main()
