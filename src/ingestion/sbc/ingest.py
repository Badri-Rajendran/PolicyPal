"""SBC ingestion: `make ingest-sbc STATES=NH,DE` (ADR 0013).

Reads the Summary of Benefits and Coverage behind every catalog plan's
`benefits_url` in the given states, so run `make ingest-plans` first. Plans
that share a URL share one document.

Incremental, never a rebuild (ADR 0015): each document is its own
transaction, and one stored by the current parser is not read again. A run
reads what is new, what an older parser stored, and any stored document whose
PDF has gone missing; recorded failures are left to `make refresh-sbc`
(ADR 0019), which also asks every stored document whether it has changed.
Every downloaded PDF is kept (ADR 0016); a replaced one is archived.
Its chunks go to `sbc_chunks`, apart from the corpus, which `make ingest`
rebuilds without touching them.

    uv run python -m src.ingestion.sbc --states NH,DE --limit 5
"""
import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import DataError
from tqdm import tqdm

from src.core.db import get_session
from src.core.logging import get_logger
from src.core.text import count_tokens
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings
from src.services.sbc_status import READ_STATUSES

from ..chunking import make_recursive_splitter
from ..constants import SBC_ARCHIVE, SBC_REJECTED
from ..plans import resolve_states, upsert
from .extract import (
    PARSER_VERSION,
    SbcParse,
    SbcParseError,
    read_parsed,
    what_is_missing,
)
from .fetch import (
    NOT_MODIFIED,
    FetchResult,
    cache_path,
    fetch_pdf,
    revalidate,
    save,
    url_key,
)
from .top_issuers import TOP_ISSUER_IDS

logger = get_logger(__name__)

_HIOS_ISSUER_ID = re.compile(r"^\d{5}$")


@dataclass(frozen=True)
class PlanRef:
    hios_plan_id: str
    name: str
    issuer: str


def documents_for(session, states: list[str], year: int,
                  issuer_ids: Collection[str] | None = None) -> dict[str, list[PlanRef]]:
    """Each distinct SBC URL among the states' plans, with the plans that point at it.

    `issuer_ids` narrows it to those HIOS issuers' plans.
    """
    stmt = (
        select(Plan.benefits_url, Plan.hios_plan_id, Plan.marketing_name, Issuer.name)
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .where(Plan.plan_year == year, Plan.state.in_(states), Plan.benefits_url.is_not(None))
        .order_by(Issuer.name, Plan.hios_plan_id)
    )
    if issuer_ids is not None:
        stmt = stmt.where(Issuer.hios_issuer_id.in_(issuer_ids))
    rows = session.execute(stmt).all()
    documents = defaultdict(list)
    for url, plan_id, name, issuer in rows:
        documents[url].append(PlanRef(plan_id, name, issuer))
    return dict(documents)


def build_chunks(url: str, year: int, parse: SbcParse) -> list[dict]:
    """One chunk per template section, split further only past the chunk size.

    Every piece starts with its section's heading, so a passage read alone
    still says what it is about.
    """
    splitter = make_recursive_splitter(settings.chunk_size, settings.chunk_overlap, separators=["\n", " ", ""])
    key = url_key(url)
    chunks = []
    for index, section in enumerate(parse.sections):
        pieces = [section.text] if count_tokens(section.text) <= settings.chunk_size else splitter.split_text(section.text)
        for piece_index, piece in enumerate(pieces):
            chunks.append({
                "chunk_id": f"sbc_{year}_{key}_s{index:02d}_c{piece_index:02d}",
                "section": section.heading[:100],
                "position": len(chunks),
                "content": f"{section.heading}\n{piece}",
            })
    return chunks


def ingest_document(url: str, year: int, stored=None) -> str:
    """Fetch, parse and store one SBC. Returns its status. The PDF is always kept."""
    _restore_rejected(url, year, stored)
    fetched = fetch_pdf(url, year)
    if fetched.status != "ok":
        _store(url, year, fetched)
        return fetched.status

    digest = hashlib.sha256(fetched.path.read_bytes()).hexdigest()
    # When the file was downloaded, not when it was last parsed (ADR 0018).
    downloaded = datetime.fromtimestamp(fetched.path.stat().st_mtime, UTC)
    try:
        pages, parse = read_parsed(fetched.path)
    except SbcParseError as exc:
        return _reject(url, year, "unparseable", str(exc), digest, downloaded)
    if parse.coverage_year != year:
        status = _reject(url, year, "wrong_year", f"coverage period starts in {parse.coverage_year}",
                         digest, downloaded)
        # Moved aside, not deleted: the issuer may correct the file at the
        # same URL, and only a fresh download would see it.
        rejected = SBC_REJECTED / str(year) / f"{fetched.path.stem}-{digest[:12]}.pdf"
        rejected.parent.mkdir(parents=True, exist_ok=True)
        fetched.path.replace(rejected)
        return status

    # Its text is kept either way: what a partial document does have is the
    # plan's own words, and the status says what it is missing (ADR 0017).
    missing = what_is_missing(parse)
    read = replace(fetched, status="partial", detail=f"missing {missing}") if missing else fetched
    try:
        _store(url, year, read, sha256=digest, pages=len(pages), title=parse.title,
               chunks=build_chunks(url, year, parse), parser_version=PARSER_VERSION, fetched_at=downloaded)
    except DataError:
        # One document the database refuses must not end a run over thousands.
        return _reject(url, year, "unparseable", "text the database refuses", digest, downloaded)
    return read.status


def _restore_rejected(url: str, year: int, stored) -> None:
    """Put a file an older parser moved aside back where documents are read from.

    A `wrong_year` file is kept in `rejected/` (ADR 0018). A parser that reads
    the coverage period differently has to judge that same file again, from
    disk, rather than ask the issuer for it a second time.
    """
    if stored is None or stored.status != "wrong_year" or not stored.sha256:
        return
    current = cache_path(url, year)
    rejected = SBC_REJECTED / str(year) / f"{current.stem}-{stored.sha256[:12]}.pdf"
    if rejected.exists() and not current.exists():
        current.parent.mkdir(parents=True, exist_ok=True)
        rejected.replace(current)


def _reject(url: str, year: int, status: str, detail: str, sha256: str, downloaded: datetime) -> str:
    """A file the parser turned down. Which file, and which parser, are kept (ADR 0018)."""
    _store(url, year, FetchResult(status, detail=detail), sha256=sha256, parser_version=PARSER_VERSION,
           fetched_at=downloaded)
    return status


def _store(url: str, year: int, fetched: FetchResult, *, sha256: str | None = None,
           pages: int | None = None, title: str | None = None, chunks: list[dict] | None = None,
           parser_version: int | None = None, fetched_at: datetime | None = None) -> None:
    """Record the attempt and replace the document's chunks, in one transaction.

    A document that fails now loses the chunks an earlier run gave it: an
    answer must never quote an SBC that is no longer the plan's. Only a file
    the parser judged keeps its parser version, so a parser change reads it
    again (ADR 0018). A fetch that failed is stamped with the attempt's time.
    """
    with get_session() as session:
        upsert(session, SbcDocument, [{
            "url": url, "plan_year": year, "status": fetched.status, "detail": fetched.detail,
            "sha256": sha256, "pages": pages, "title": title, "fetched_at": fetched_at or datetime.now(UTC),
            "parser_version": parser_version,
        }], "uq_sbc_documents_url_plan_year", ("url", "plan_year"))
        document_id = session.scalar(
            select(SbcDocument.id).where(SbcDocument.url == url, SbcDocument.plan_year == year)
        )
        session.execute(delete(SbcChunk).where(SbcChunk.document_id == document_id))
        if chunks:
            session.execute(insert(SbcChunk), [{**chunk, "document_id": document_id} for chunk in chunks])


def refresh_document(url: str, year: int, stored) -> str:
    """Ask the issuer whether a stored document has changed, and follow ADR 0019.

    The reply is compared in memory, so a file is only ever written when it
    really is a new one, and the file it replaces is archived, never deleted.
    """
    fetched = revalidate(url, stored.etag, stored.last_modified)
    if fetched.status == NOT_MODIFIED:
        _checked(url, year)
        return "unchanged"
    if fetched.transient:
        # A 5xx, a 429 or a network error says nothing about the document:
        # its text stays, and the next refresh asks again.
        return "unreachable"
    if fetched.status != "ok":
        _archive(url, year)
        _store(url, year, fetched)
        return fetched.status

    if hashlib.sha256(fetched.body).hexdigest() == stored.sha256 and cache_path(url, year).exists():
        _checked(url, year, fetched)
        return "unchanged"

    _archive(url, year, stored.sha256)
    save(fetched.body, cache_path(url, year))
    status = ingest_document(url, year)
    _checked(url, year, fetched)
    return f"changed:{status}"


def _archive(url: str, year: int, sha256: str | None = None) -> None:
    """Move the file a new one replaces out of the cache, keeping it for good (ADR 0016)."""
    current = cache_path(url, year)
    if not current.exists():
        return
    digest = sha256 or hashlib.sha256(current.read_bytes()).hexdigest()
    archived = SBC_ARCHIVE / str(year) / f"{current.stem}-{digest[:12]}.pdf"
    archived.parent.mkdir(parents=True, exist_ok=True)
    current.replace(archived)


def _checked(url: str, year: int, fetched: FetchResult | None = None) -> None:
    """Record that the document was asked about, and what to ask with next time."""
    values = {"checked_at": datetime.now(UTC)}
    if fetched:
        values |= {"etag": fetched.etag, "last_modified": fetched.last_modified}
    with get_session() as session:
        session.execute(update(SbcDocument)
                        .where(SbcDocument.url == url, SbcDocument.plan_year == year)
                        .values(**values))


def _needs_reading(url: str, row, year: int, refresh: bool) -> bool:
    """Whether this run reads the document: new, outdated, its PDF gone, or a refresh.

    A recorded failure is left alone unless this is a refresh: re-asking a
    blocked host on every run costs time and puts load on it for nothing.
    """
    if row is None or refresh:
        return True
    if row.status not in (*READ_STATUSES, "unparseable", "wrong_year"):
        return False
    return (row.parser_version != PARSER_VERSION
            or (row.status in READ_STATUSES and not cache_path(url, year).exists()))


def execute(states: list[str], year: int, limit: int | None = None,
            issuer_ids: Collection[str] | None = None, refresh: bool = False) -> Counter:
    """Read what is new or outdated; with `refresh`, ask about every stored document too.

    Returns what happened to each document read.
    """
    with get_session() as session:
        documents = documents_for(session, states, year, issuer_ids)
        stored = {row.url: row for row in session.execute(
            select(SbcDocument.url, SbcDocument.status, SbcDocument.parser_version, SbcDocument.sha256,
                   SbcDocument.etag, SbcDocument.last_modified).where(SbcDocument.plan_year == year)
        ).all()}
    if not documents:
        sys.exit(f"No catalog plans with an SBC link for {', '.join(states)} in {year}. "
                 f"Run `make ingest-plans STATES={','.join(states)}` first.")
    pending = [url for url in documents if _needs_reading(url, stored.get(url), year, refresh)]
    urls = pending[:limit]
    skipped = sum(1 for url in documents
                  if url not in pending and stored.get(url) and stored[url].status != "ok")
    print(f"{len(documents)} SBC documents behind the {', '.join(states)} plans for {year}; "
          f"{len(documents) - len(pending)} already current, "
          f"{'re-checking' if refresh else 'reading'} {len(urls)}")
    if skipped:
        print(f"{skipped} recorded failures skipped; `make refresh-sbc STATES={','.join(states)}` retries them")

    statuses = Counter()
    failures = defaultdict(list)   # (issuer, status) -> plans
    for url in tqdm(urls, desc="SBCs"):
        row = stored.get(url)
        status = refresh_document(url, year, row) if refresh and row and row.status in READ_STATUSES \
            else ingest_document(url, year, row)
        statuses[status] += 1
        if status not in ("ok", "partial", "unchanged", "changed:ok", "changed:partial", "unreachable"):
            for plan in documents[url]:
                failures[(plan.issuer, status)].append(plan)

    if statuses:
        print("\n" + ", ".join(f"{count} {status}" for status, count in statuses.most_common()))
    if failures:
        print("\nPlans without a usable SBC (answers link their PDF instead):")
        for (issuer, status), plans in sorted(failures.items()):
            sample = ", ".join(p.hios_plan_id for p in plans[:3]) + (" …" if len(plans) > 3 else "")
            print(f"  {issuer}: {len(plans)} plans, {status} ({sample})")
        print("\nA blocked host refused automated requests and is not retried around. "
              "Other failures are retried by `make refresh-sbc`.")
    logger.info("SBC ingest finished: %s", dict(statuses))
    return statuses


def parse_args(args):
    parser = argparse.ArgumentParser(description="Ingest Summary of Benefits and Coverage PDFs for catalog plans.")
    parser.add_argument("--states", required=True, help="Comma-separated state codes, or ALL, e.g. NH,DE")
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year,
                        help="Plan year (default: this year); must match an ingested catalog year")
    parser.add_argument("--limit", type=int, default=None, help="Read at most this many documents, for a smoke run")
    parser.add_argument("--refresh", action="store_true",
                        help="Also ask every stored document whether it has changed, and retry failures")
    issuers = parser.add_mutually_exclusive_group()
    issuers.add_argument("--top-issuers", action="store_true",
                         help="Only the largest parent companies' plans (src/ingestion/sbc/top_issuers.py)")
    issuers.add_argument("--issuers", help="Only these HIOS issuer IDs' plans, comma-separated, e.g. 40788,66252")
    parsed = parser.parse_args(args)
    try:
        parsed.states = resolve_states(parsed.states)
    except ValueError as exc:
        parser.error(str(exc))
    if parsed.limit is not None and parsed.limit < 1:
        parser.error("--limit must be at least 1")
    parsed.issuer_ids = TOP_ISSUER_IDS if parsed.top_issuers else None
    if parsed.issuers is not None:
        parsed.issuer_ids = frozenset(i.strip() for i in parsed.issuers.split(",") if i.strip())
        if not parsed.issuer_ids or not all(_HIOS_ISSUER_ID.match(i) for i in parsed.issuer_ids):
            parser.error("--issuers takes five-digit HIOS issuer IDs, e.g. 40788,66252")
    return parsed


def main(args=sys.argv[1:]) -> None:
    parsed = parse_args(args)
    execute(parsed.states, parsed.year, parsed.limit, parsed.issuer_ids, parsed.refresh)
