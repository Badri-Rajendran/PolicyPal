"""California's SBC links: a committed, hand-built list, and the commands around it (ADR 0026).

CMS's California PUF has no SBC links, so every California plan's link comes
from `manifests/ca-<year>.csv`: which carrier document is which plan's, found
and checked by a person. Each row's host must have an `sbc_host` entry in the
source registry. Disabling that entry and applying again unlinks its plans,
which is how a carrier is removed.

    uv run python -m src.ingestion.sbc.manifest apply --year 2026
    uv run python -m src.ingestion.sbc.manifest check --year 2026
"""
import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select, update

from src.core.db import get_session
from src.core.logging import get_logger
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcDocument
from src.services.sbc_status import READ_STATUSES, plan_sbc_status, sbc_document_join

from ..ca_puf.load import CATALOG_SOURCE
from ..sources.registry import host_access, sbc_host_for
from .fetch import unsafe_reason

logger = get_logger(__name__)

MANIFEST_DIR = Path(__file__).with_name("manifests")
COLUMNS = ("hios_plan_id", "plan_year", "sbc_url", "verified_on", "note")
_PLAN_ID = re.compile(r"^\d{5}CA\d{7}$")
_WORD = re.compile(r"[a-z0-9]+")


class ManifestError(ValueError):
    """The manifest breaks a rule; nothing was applied. The message names the line."""


@dataclass(frozen=True)
class ManifestRow:
    hios_plan_id: str
    sbc_url: str
    verified_on: date
    note: str


@dataclass(frozen=True)
class ApplyReport:
    linked: int                       # plans given a link
    documents: int                    # distinct links among them
    unlisted: tuple[str, ...]         # loaded plans with no row: no link
    disabled: dict[str, int]          # registry entry -> plans left unlinked because it is disabled


def manifest_path(year: int) -> Path:
    return MANIFEST_DIR / f"ca-{year}.csv"


def load_manifest(path: Path, year: int) -> tuple[ManifestRow, ...]:
    """The manifest's rows, every one checked; raises ManifestError on the first bad line."""
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ManifestError(f"{path.name}: the header must be {','.join(COLUMNS)}")
            rows = [_row(raw, reader.line_num, year) for raw in reader]
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestError(f"{path.name} could not be read: {exc}") from None
    seen = Counter(row.hios_plan_id for row in rows)
    if twice := sorted(plan for plan, count in seen.items() if count > 1):
        raise ManifestError(f"{path.name}: plan {twice[0]} is listed more than once")
    return tuple(rows)


def _row(raw: dict, line: int, year: int) -> ManifestRow:
    where = f"line {line}"
    if None in raw or any(value is None for value in raw.values()):
        raise ManifestError(f"{where}: expected {len(COLUMNS)} columns")
    plan_id, url = raw["hios_plan_id"].strip(), raw["sbc_url"].strip()
    if not _PLAN_ID.match(plan_id):
        raise ManifestError(f"{where}: {plan_id!r} is not a California base plan ID (e.g. 40513CA0380003)")
    if raw["plan_year"].strip() != str(year):
        raise ManifestError(f"{where}: plan year {raw['plan_year']!r} is not {year}")
    if reason := unsafe_reason(url):
        raise ManifestError(f"{where}: the link is {reason}")
    entry = sbc_host_for(url)
    if entry is None or entry.jurisdiction != "CA":
        raise ManifestError(f"{where}: no California sbc_host entry in the source registry covers {url}")
    try:
        verified = date.fromisoformat(raw["verified_on"].strip())
    except ValueError:
        raise ManifestError(f"{where}: verified_on must be a date, e.g. 2026-09-25") from None
    return ManifestRow(plan_id, url, verified, raw["note"].strip())


def apply_manifest(session, rows: tuple[ManifestRow, ...], year: int) -> ApplyReport:
    """Set every California plan's link for the year from the manifest; the caller commits.

    Authoritative: a plan with no row, or whose row's host is disabled, is left
    with no link, so a removed row or carrier stops being read.
    """
    plans = dict(session.execute(
        select(Plan.hios_plan_id, Plan.id).where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE)
    ).all())
    if unknown := sorted({row.hios_plan_id for row in rows} - set(plans)):
        raise ManifestError(f"plan {unknown[0]} is in the manifest but not among the {year} California plans")

    by_plan = {row.hios_plan_id: row for row in rows}
    links: dict[str, str | None] = {}
    disabled: Counter = Counter()
    for plan_id in plans:
        row = by_plan.get(plan_id)
        if row is not None and host_access(row.sbc_url) is None:
            disabled[sbc_host_for(row.sbc_url).id] += 1
            row = None
        links[plan_id] = row.sbc_url if row else None

    if plans:
        session.execute(update(Plan), [{"id": plans[plan_id], "benefits_url": url} for plan_id, url in links.items()])
    linked = {url for url in links.values() if url}
    return ApplyReport(linked=sum(1 for url in links.values() if url), documents=len(linked),
                       unlisted=tuple(sorted(plan for plan in plans if plan not in by_plan)), disabled=dict(disabled))


def apply_for_year(year: int) -> ApplyReport | None:
    """Load and apply the year's manifest in its own transaction; None when there is none."""
    path = manifest_path(year)
    if not path.exists():
        return None
    rows = load_manifest(path, year)
    with get_session() as session:
        return apply_manifest(session, rows, year)


def print_apply(report: ApplyReport, year: int) -> None:
    print(f"{report.linked} California plans for {year} linked to {report.documents} SBC documents; "
          f"{len(report.unlisted)} not in the manifest, so shown with no link")
    for source, count in sorted(report.disabled.items()):
        print(f"  {count} plans unlinked: registry entry {source} is disabled")
    logger.info("sbc manifest applied for %d: %d plans, %d documents", year, report.linked, report.documents)


def name_matches(marketing_name: str, printed_title: str | None) -> bool:
    """Whether every word of the plan's name is printed in the SBC's title.

    A cheap guard against a row pointing at the wrong plan's document; a person
    judges each mismatch, since carriers print names their own way.
    """
    return bool(printed_title) and set(_WORD.findall(marketing_name.lower())) <= set(
        _WORD.findall(printed_title.lower()))


@dataclass
class CheckReport:
    """What a person should look at after an ingest. Each list holds (issuer, plan ID, name, …) rows."""
    read: int = 0
    manual: int = 0                   # of `read`, how many came from a manual import
    name_mismatch: list[tuple] = field(default_factory=list)
    failed: list[tuple] = field(default_factory=list)
    awaiting_import: list[tuple] = field(default_factory=list)
    not_read: list[tuple] = field(default_factory=list)
    no_link: list[tuple] = field(default_factory=list)


def check(session, year: int) -> CheckReport:
    """Every California plan of the year, sorted into what needs a person's eye; reads only."""
    rows = session.execute(
        select(Plan.hios_plan_id, Plan.marketing_name, Plan.benefits_url, Issuer.name, plan_sbc_status(),
               SbcDocument.title, SbcDocument.acquisition)
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .outerjoin(SbcDocument, sbc_document_join())
        .where(Plan.plan_year == year, Plan.catalog_source == CATALOG_SOURCE)
        .order_by(Issuer.name, Plan.hios_plan_id)
    ).all()
    report = CheckReport()
    for plan_id, name, url, issuer, status, title, acquisition in rows:
        plan = (issuer, plan_id, name)
        if status == "no_link":
            report.no_link.append(plan)
        elif status == "not_read":
            (report.awaiting_import if host_access(url) == "manual" else report.not_read).append(plan)
        elif status not in READ_STATUSES:
            report.failed.append((*plan, status))
        else:
            report.read += 1
            report.manual += acquisition == "manual"
            if not name_matches(name, title):
                report.name_mismatch.append((*plan, title))
    return report


def print_check(report: CheckReport, year: int) -> None:
    print(f"California SBCs for {year}: {report.read} plans read ({report.manual} from manual imports)")
    sections = (
        (report.name_mismatch, "Printed title doesn't carry the plan's name: check the row points at the right document"),
        (report.failed, "Linked, but the document could not be read"),
        (report.awaiting_import, "Awaiting `make import-sbc` (the carrier's documents are manual-only)"),
        (report.not_read, "Linked, not read yet: run `make ingest-sbc STATES=CA`"),
        (report.no_link, "No link in the manifest"),
    )
    for plans, heading in sections:
        if plans:
            print(f"\n{heading}: {len(plans)}")
            for plan in plans:
                print("  " + " | ".join(str(value) for value in plan))


def parse_args(args):
    parser = argparse.ArgumentParser(description="Apply or check California's SBC manifest.")
    parser.add_argument("command", choices=("apply", "check"))
    parser.add_argument("--year", type=int, required=True, help="Plan year, e.g. 2026")
    return parser.parse_args(args)


def main(args=sys.argv[1:]) -> None:
    parsed = parse_args(args)
    if parsed.command == "check":
        with get_session() as session:
            print_check(check(session, parsed.year), parsed.year)
        return
    try:
        report = apply_for_year(parsed.year)
    except ManifestError as exc:
        sys.exit(f"SBC manifest not applied: {exc}")
    if report is None:
        sys.exit(f"No manifest for {parsed.year}: expected {manifest_path(parsed.year)}")
    print_apply(report, parsed.year)


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    main()
