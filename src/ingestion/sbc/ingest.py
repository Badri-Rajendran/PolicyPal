"""SBC ingestion: `make ingest-sbc STATES=NH,DE` (ADR 0013).

Reads the Summary of Benefits and Coverage behind every catalog plan's
`benefits_url` in the given states, so run `make ingest-plans` first. Plans
that share a URL share one document.

Incremental, never a rebuild (ADR 0015): each document is its own
transaction, one stored by the current parser is not read again, and anything
that failed is tried again next run. A PDF is deleted once its text is
stored, unless `--keep-pdfs` asks to keep it for tuning the parser.
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
from .extract import PARSER_VERSION, SbcParse, SbcParseError, parse_sbc, read_pdf
from .fetch import FetchResult, cache_path, fetch_pdf, url_key
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


def ingest_document(url: str, year: int, keep_pdf: bool = False) -> str:
    """Fetch, parse and store one SBC. Returns its status.

    The PDF is deleted once its text is committed; `keep_pdf` keeps it, and
    an unparseable one too, so parser fixes can be tried without a download.
    """
    fetched = fetch_pdf(url, year)
    if fetched.status != "ok":
        _store(url, year, fetched)
        return fetched.status

    digest = hashlib.sha256(fetched.path.read_bytes()).hexdigest()
    try:
        pages = read_pdf(fetched.path)
        parse = parse_sbc(pages)
    except SbcParseError as exc:
        return _reject(url, year, fetched, "unparseable", str(exc), discard=not keep_pdf)
    if parse.coverage_year != year:
        # Always discarded: the issuer may correct the file at the same URL,
        # and only a fresh download would see it.
        return _reject(url, year, fetched, "wrong_year", f"coverage period starts in {parse.coverage_year}")

    _store(url, year, fetched, sha256=digest, pages=len(pages), title=parse.title,
           chunks=build_chunks(url, year, parse), parser_version=PARSER_VERSION)
    if not keep_pdf:
        fetched.path.unlink(missing_ok=True)
    return "ok"


def _reject(url: str, year: int, fetched: FetchResult, status: str, detail: str, discard: bool = True) -> str:
    _store(url, year, FetchResult(status, detail=detail))
    if discard:
        fetched.path.unlink(missing_ok=True)
    return status


def _store(url: str, year: int, fetched: FetchResult, *, sha256: str | None = None,
           pages: int | None = None, title: str | None = None, chunks: list[dict] | None = None,
           parser_version: int | None = None) -> None:
    """Record the attempt and replace the document's chunks, in one transaction.

    A document that fails now loses the chunks an earlier run gave it, and
    its parser version: an answer must never quote an SBC that is no longer
    the plan's, and the next run must try it again.
    """
    with get_session() as session:
        upsert(session, SbcDocument, [{
            "url": url, "plan_year": year, "status": fetched.status, "detail": fetched.detail,
            "sha256": sha256, "pages": pages, "title": title, "fetched_at": datetime.now(UTC),
            "parser_version": parser_version,
        }], "uq_sbc_documents_url_plan_year", ("url", "plan_year"))
        document_id = session.scalar(
            select(SbcDocument.id).where(SbcDocument.url == url, SbcDocument.plan_year == year)
        )
        session.execute(delete(SbcChunk).where(SbcChunk.document_id == document_id))
        if chunks:
            session.execute(insert(SbcChunk), [{**chunk, "document_id": document_id} for chunk in chunks])


def execute(states: list[str], year: int, limit: int | None = None,
            issuer_ids: Collection[str] | None = None, keep_pdfs: bool = False) -> Counter:
    """Read every document not already stored by this parser. Returns the statuses of those read."""
    with get_session() as session:
        documents = documents_for(session, states, year, issuer_ids)
        current = set(session.scalars(select(SbcDocument.url).where(
            SbcDocument.plan_year == year, SbcDocument.status == "ok",
            SbcDocument.parser_version == PARSER_VERSION,
        )))
    if not documents:
        sys.exit(f"No catalog plans with an SBC link for {', '.join(states)} in {year}. "
                 f"Run `make ingest-plans STATES={','.join(states)}` first.")
    pending = [url for url in documents if url not in current]
    if not keep_pdfs:
        # A tuning run keeps the PDFs of what it stored; the next run removes them.
        for url in documents.keys() & current:
            cache_path(url, year).unlink(missing_ok=True)
    urls = pending[:limit]
    print(f"{len(documents)} SBC documents behind the {', '.join(states)} plans for {year}; "
          f"{len(documents) - len(pending)} already current, reading {len(urls)}")

    statuses = Counter()
    failures = defaultdict(list)   # (issuer, status) -> plans
    for url in tqdm(urls, desc="SBCs"):
        status = ingest_document(url, year, keep_pdfs)
        statuses[status] += 1
        if status != "ok":
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
              "Other failures are retried on the next run.")
    logger.info("SBC ingest finished: %s", dict(statuses))
    return statuses


def parse_args(args):
    parser = argparse.ArgumentParser(description="Ingest Summary of Benefits and Coverage PDFs for catalog plans.")
    parser.add_argument("--states", required=True, help="Comma-separated state codes, or ALL, e.g. NH,DE")
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year,
                        help="Plan year (default: this year); must match an ingested catalog year")
    parser.add_argument("--limit", type=int, default=None, help="Read at most this many documents, for a smoke run")
    issuers = parser.add_mutually_exclusive_group()
    issuers.add_argument("--top-issuers", action="store_true",
                         help="Only the largest parent companies' plans (src/ingestion/sbc/top_issuers.py)")
    issuers.add_argument("--issuers", help="Only these HIOS issuer IDs' plans, comma-separated, e.g. 40788,66252")
    parser.add_argument("--keep-pdfs", action="store_true",
                        help="Keep downloaded PDFs after parsing, for tuning the parser")
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
    execute(parsed.states, parsed.year, parsed.limit, parsed.issuer_ids, parsed.keep_pdfs)
