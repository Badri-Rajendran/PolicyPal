"""SBC ingestion: `make ingest-sbc STATES=NH,DE` (ADR 0013).

Reads the Summary of Benefits and Coverage behind every catalog plan's
`benefits_url` in the given states, so run `make ingest-plans` first. Plans
that share a URL share one document.

Incremental, never a rebuild: each document is its own transaction, a
downloaded PDF is never downloaded again, and anything that failed is tried
again next run.
Its chunks go to `sbc_chunks`, apart from the corpus, which `make ingest`
rebuilds without touching them.

    uv run python -m src.ingestion.sbc --states NH,DE --limit 5
"""
import argparse
import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, insert, select
from tqdm import tqdm

from src.core.db import get_session
from src.core.logging import get_logger
from src.core.text import count_tokens
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings

from ..chunking import make_recursive_splitter
from ..plans import resolve_states, upsert
from .extract import SbcParse, SbcParseError, parse_sbc, read_pdf
from .fetch import FetchResult, fetch_pdf, url_key

logger = get_logger(__name__)


@dataclass(frozen=True)
class PlanRef:
    hios_plan_id: str
    name: str
    issuer: str


def documents_for(session, states: list[str], year: int) -> dict[str, list[PlanRef]]:
    """Each distinct SBC URL among the states' plans, with the plans that point at it."""
    rows = session.execute(
        select(Plan.benefits_url, Plan.hios_plan_id, Plan.marketing_name, Issuer.name)
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .where(Plan.plan_year == year, Plan.state.in_(states), Plan.benefits_url.is_not(None))
        .order_by(Issuer.name, Plan.hios_plan_id)
    ).all()
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


def ingest_document(url: str, year: int) -> str:
    """Fetch, parse and store one SBC. Returns its status."""
    fetched = fetch_pdf(url, year)
    if fetched.status != "ok":
        _store(url, year, fetched)
        return fetched.status

    # Parsed again on every run, from the cached file: a fix to the parser
    # must reach documents stored before it, and the cache already spares
    # the issuer a second download.
    digest = hashlib.sha256(fetched.path.read_bytes()).hexdigest()
    try:
        pages = read_pdf(fetched.path)
        parse = parse_sbc(pages)
    except SbcParseError as exc:
        return _reject(url, year, fetched, "unparseable", str(exc))
    if parse.coverage_year != year:
        return _reject(url, year, fetched, "wrong_year", f"coverage period starts in {parse.coverage_year}")

    _store(url, year, fetched, sha256=digest, pages=len(pages), title=parse.title,
           chunks=build_chunks(url, year, parse))
    return "ok"


def _reject(url: str, year: int, fetched: FetchResult, status: str, detail: str) -> str:
    # The cached copy goes too: the issuer may correct the file at the same
    # URL, and only a fresh download would see it.
    fetched.path.unlink(missing_ok=True)
    _store(url, year, FetchResult(status, detail=detail))
    return status


def _store(url: str, year: int, fetched: FetchResult, *, sha256: str | None = None,
           pages: int | None = None, title: str | None = None, chunks: list[dict] | None = None) -> None:
    """Record the attempt and replace the document's chunks, in one transaction.

    A document that fails now loses the chunks an earlier run gave it: an
    answer must never quote an SBC that is no longer the plan's.
    """
    with get_session() as session:
        upsert(session, SbcDocument, [{
            "url": url, "plan_year": year, "status": fetched.status, "detail": fetched.detail,
            "sha256": sha256, "pages": pages, "title": title, "fetched_at": datetime.now(UTC),
        }], "uq_sbc_documents_url_plan_year", ("url", "plan_year"))
        document_id = session.scalar(
            select(SbcDocument.id).where(SbcDocument.url == url, SbcDocument.plan_year == year)
        )
        session.execute(delete(SbcChunk).where(SbcChunk.document_id == document_id))
        if chunks:
            session.execute(insert(SbcChunk), [{**chunk, "document_id": document_id} for chunk in chunks])


def execute(states: list[str], year: int, limit: int | None = None) -> Counter:
    with get_session() as session:
        documents = documents_for(session, states, year)
    urls = list(documents)[:limit]
    print(f"{len(documents)} SBC documents behind the {', '.join(states)} plans for {year}; reading {len(urls)}")

    statuses = Counter()
    failures = defaultdict(list)   # (issuer, status) -> plans
    for url in tqdm(urls, desc="SBCs"):
        status = ingest_document(url, year)
        statuses[status] += 1
        if status != "ok":
            for plan in documents[url]:
                failures[(plan.issuer, status)].append(plan)

    print("\n" + ", ".join(f"{count} {status}" for status, count in statuses.most_common()))
    if failures:
        print("\nPlans without a usable SBC (answers link their PDF instead):")
        for (issuer, status), plans in sorted(failures.items()):
            sample = ", ".join(p.hios_plan_id for p in plans[:3]) + (" …" if len(plans) > 3 else "")
            print(f"  {issuer}: {len(plans)} plans, {status} ({sample})")
        print("\nA blocked host refused automated requests and is not retried around. "
              "Other failures are retried on the next run.")
    logger.info("SBC ingest finished: %s", dict(statuses))
    return statuses


def parse_args(args):
    parser = argparse.ArgumentParser(description="Ingest Summary of Benefits and Coverage PDFs for catalog plans.")
    parser.add_argument("--states", required=True, help="Comma-separated state codes, or ALL, e.g. NH,DE")
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year,
                        help="Plan year (default: this year); must match an ingested catalog year")
    parser.add_argument("--limit", type=int, default=None, help="Read at most this many documents, for a smoke run")
    parsed = parser.parse_args(args)
    try:
        parsed.states = resolve_states(parsed.states)
    except ValueError as exc:
        parser.error(str(exc))
    if parsed.limit is not None and parsed.limit < 1:
        parser.error("--limit must be at least 1")
    return parsed


def main(args=sys.argv[1:]) -> None:
    parsed = parse_args(args)
    if not execute(parsed.states, parsed.year, parsed.limit):
        sys.exit(f"No catalog plans with an SBC link for {', '.join(parsed.states)} in {parsed.year}. "
                 f"Run `make ingest-plans STATES={','.join(parsed.states)}` first.")
