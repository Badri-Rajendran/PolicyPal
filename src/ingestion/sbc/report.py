"""What SBC coverage there is, and what is missing: `make sbc-report` (Phase 4).

At this scale "did ingestion work?" is not answerable by eye. This counts, for
a plan year, how many catalog plans have a Summary of Benefits with text
behind them, how many don't and why, per state and per issuer. It reads and
writes nothing.

    make sbc-report YEAR=2026
    make sbc-report YEAR=2026 STATES=FL,TX VERIFY=1
"""
import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from src.core.db import get_session
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcDocument
from src.services.sbc_status import READ_STATUSES, plan_sbc_status, sbc_document_join

from ..constants import SBC_ARCHIVE, SBC_RAW, SBC_REJECTED
from ..plans import resolve_states
from .extract import PARSER_VERSION
from .fetch import cache_path
from .top_issuers import TOP_ISSUERS

# A plan the latest catalog run for its state did not return again. The run
# writes county by county over minutes, so only a day's gap counts.
STALE_AFTER = timedelta(days=1)

_PARENTS = {issuer_id: parent for parent, ids in TOP_ISSUERS.items() for issuer_id in ids}


@dataclass
class Coverage:
    """How many plans have their document's text, and what stopped the rest."""

    plans: int = 0
    statuses: Counter = field(default_factory=Counter)

    @property
    def read(self) -> int:
        """Plans with searchable text, counted as the rest of the app counts it.

        `partial` is read: its text is stored, searched and quoted. Counting
        only `ok` here made the report disagree with the plan card and the
        answer the user sees.
        """
        return sum(self.statuses[status] for status in READ_STATUSES)

    def add(self, status: str, plans: int) -> None:
        self.plans += plans
        self.statuses[status] += plans


@dataclass
class Report:
    year: int
    states: list[str]
    total: Coverage
    by_state: dict[str, Coverage]
    by_issuer: dict[tuple[str, str], Coverage]   # (parent, issuer) -> coverage
    reasons: Counter                              # (status, detail) -> documents
    orphans: Counter                              # status -> documents no plan points at
    outdated: int                                 # documents stored by an older parser
    stale_plans: dict[str, int]                   # state -> plans the latest run didn't return
    files: dict[str, tuple[int, int]]             # folder -> (files, bytes)
    missing_files: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)


def collect(session, year: int, states: list[str] | None = None, verify: bool = False) -> Report:
    status = plan_sbc_status().label("sbc_status")
    rows = session.execute(
        select(Plan.state, Issuer.hios_issuer_id, Issuer.name, status, func.count())
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .outerjoin(SbcDocument, sbc_document_join())
        .where(Plan.plan_year == year, *([Plan.state.in_(states)] if states else []))
        .group_by(Plan.state, Issuer.hios_issuer_id, Issuer.name, status)
    ).all()

    total, by_state, by_issuer = Coverage(), defaultdict(Coverage), defaultdict(Coverage)
    for state, issuer_id, issuer, status, plans in rows:
        total.add(status, plans)
        by_state[state].add(status, plans)
        by_issuer[(_PARENTS.get(issuer_id, ""), f"{issuer} ({issuer_id})")].add(status, plans)

    return Report(
        year=year,
        states=states or sorted(by_state),
        total=total,
        by_state=dict(sorted(by_state.items())),
        by_issuer=dict(sorted(by_issuer.items())),
        reasons=_reasons(session, year),
        orphans=_orphans(session, year),
        outdated=session.scalar(
            select(func.count()).select_from(SbcDocument)
            .where(SbcDocument.plan_year == year, SbcDocument.status.in_(READ_STATUSES),
                   SbcDocument.parser_version != PARSER_VERSION)
        ),
        stale_plans=_stale_plans(session, year, states),
        files=_files(year),
        **_verify(session, year) if verify else {},
    )


def _reasons(session, year: int) -> Counter:
    rows = session.execute(
        select(SbcDocument.status, SbcDocument.detail, func.count())
        .where(SbcDocument.plan_year == year, SbcDocument.status.notin_(READ_STATUSES))
        .group_by(SbcDocument.status, SbcDocument.detail)
    ).all()
    return Counter({(status, detail): count for status, detail, count in rows})


def _orphans(session, year: int) -> Counter:
    """Documents no catalog plan points at: the plans moved to another link, or left."""
    rows = session.execute(
        select(SbcDocument.status, func.count())
        .where(SbcDocument.plan_year == year, ~select(Plan.id).where(
            Plan.benefits_url == SbcDocument.url, Plan.plan_year == year).exists())
        .group_by(SbcDocument.status)
    ).all()
    return Counter(dict(rows))


def _stale_plans(session, year: int, states: list[str] | None) -> dict[str, int]:
    """Per state, plans the latest catalog run did not write again (ADR 0019 reports, never removes)."""
    latest = (
        select(Plan.state, func.max(Plan.updated_at).label("latest"))
        .where(Plan.plan_year == year, *([Plan.state.in_(states)] if states else []))
        .group_by(Plan.state)
        .subquery()
    )
    rows = session.execute(
        select(latest.c.state, func.count())
        .join(Plan, (Plan.state == latest.c.state) & (Plan.plan_year == year))
        .where(Plan.updated_at < latest.c.latest - STALE_AFTER)
        .group_by(latest.c.state)
    ).all()
    return dict(rows)


def _files(year: int) -> dict[str, tuple[int, int]]:
    folders = {}
    for name, folder in (("raw", SBC_RAW), ("rejected", SBC_REJECTED), ("archive", SBC_ARCHIVE)):
        files = sorted((folder / str(year)).glob("*.pdf"))
        folders[name] = (len(files), sum(f.stat().st_size for f in files))
    return folders


def _verify(session, year: int) -> dict:
    """Each stored document's file, checked against the hash recorded when it was parsed."""
    missing, changed = [], []
    documents = session.execute(
        select(SbcDocument.url, SbcDocument.sha256)
        .where(SbcDocument.plan_year == year, SbcDocument.status.in_(READ_STATUSES))
    ).all()
    for url, sha256 in documents:
        path = cache_path(url, year)
        if not path.exists():
            missing.append(url)
        elif sha256 and hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            changed.append(url)
    return {"missing_files": missing, "changed_files": changed}


def _line(name: str, coverage: Coverage) -> str:
    share = f"{100 * coverage.read / coverage.plans:5.1f}%" if coverage.plans else "    -"
    missing = ", ".join(f"{count} {status}" for status, count in coverage.statuses.most_common()
                        if status not in READ_STATUSES)
    return f"  {name[:52]:<52} {coverage.plans:>6} {coverage.read:>6} {share}  {missing}"


def render(report: Report) -> str:
    out = [f"SBC coverage for {report.year}, {', '.join(report.states) or 'no states'}",
           f"{'':>54} {'plans':>6} {'read':>6}  share  missing", _line("ALL", report.total), "", "By state:"]
    out += [_line(state, coverage) for state, coverage in report.by_state.items()]

    out += ["", "By issuer:"]
    for (parent, issuer), coverage in sorted(report.by_issuer.items()):
        out.append(_line(f"{issuer}{f'  [{parent}]' if parent else ''}", coverage))

    if report.reasons:
        out += ["", "Why documents could not be read:"]
        out += [f"  {count:>6}  {status}: {detail}" for (status, detail), count in report.reasons.most_common()]

    out += ["", f"Documents stored by an older parser (current is {PARSER_VERSION}): {report.outdated}"]
    if report.orphans:
        out.append("Documents no plan points at (the plans moved link, or left): "
                   + ", ".join(f"{count} {status}" for status, count in report.orphans.most_common()))
    if report.stale_plans:
        out.append("Plans the latest catalog run did not return: "
                   + ", ".join(f"{state} {count}" for state, count in sorted(report.stale_plans.items())))

    out.append("Kept PDFs: " + ", ".join(
        f"{name} {files} files, {size / 1_048_576:.0f} MB" for name, (files, size) in report.files.items()))
    if report.missing_files or report.changed_files:
        out.append(f"Files missing: {len(report.missing_files)}; files whose hash changed: {len(report.changed_files)}")
    return "\n".join(out)


def parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--states", help="Comma-separated state codes, or ALL; default every state with plans")
    parser.add_argument("--verify-files", action="store_true",
                        help="Also hash every stored PDF and report any missing or changed")
    parsed = parser.parse_args(args)
    try:
        parsed.states = resolve_states(parsed.states) if parsed.states else None
    except ValueError as exc:
        parser.error(str(exc))
    return parsed


def main(args=sys.argv[1:]) -> None:
    parsed = parse_args(args)
    with get_session() as session:
        print(render(collect(session, parsed.year, parsed.states, parsed.verify_files)))


if __name__ == "__main__":
    main()
