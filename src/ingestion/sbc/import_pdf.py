"""`make import-sbc`: read an SBC that a person downloaded in a browser (ADR 0026).

Some carriers refuse automated requests (robots.txt, a 403) or name AI
crawlers as unwelcome. The crawler never works around that. A person may still
open the carrier's page and download the plan's SBC, as any shopper would, and
this reads that file: it is copied into the cache under the plan's link, and
parsed exactly as a crawled one, with no request made. It is recorded as
`manual`, so no ingest or refresh ever asks the carrier for it.

    uv run python -m src.ingestion.sbc.import_pdf --year 2026 --file ~/Downloads/x.pdf --url https://…/x.pdf
    uv run python -m src.ingestion.sbc.import_pdf --year 2026 --dir ~/Downloads/ca-sbc
"""
import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, unquote, urlsplit

from sqlalchemy import select

from src.core.db import get_session
from src.core.logging import get_logger
from src.models.plan import Plan
from src.models.sbc import SbcDocument

from ..sources.registry import host_access
from .fetch import MAX_BYTES, cache_path, looks_like_pdf, save
from .ingest import archive, ingest_document

logger = get_logger(__name__)


class SbcImportError(ValueError):
    """The file or link can't be imported; nothing was written. The message says why."""


def _linked(year: int) -> set[str]:
    with get_session() as session:
        return set(session.scalars(
            select(Plan.benefits_url).where(Plan.plan_year == year, Plan.benefits_url.is_not(None)).distinct()
        ))


def import_file(path: Path, url: str, year: int, linked: set[str] | None = None) -> str:
    """Import one downloaded PDF as the document behind `url`. Returns its status."""
    if url not in (linked if linked is not None else _linked(year)):
        raise SbcImportError(f"no {year} plan links to {url}; apply the SBC manifest first")
    if host_access(url) is None:
        raise SbcImportError(f"{url}: its host has no enabled sbc_host entry in the source registry")
    if not path.is_file():
        raise SbcImportError(f"{path} is not a file")
    if path.stat().st_size > MAX_BYTES:
        raise SbcImportError(f"{path.name} is over {MAX_BYTES // (1024 * 1024)} MB; not a Summary of Benefits")
    body = path.read_bytes()
    if not looks_like_pdf(body):
        raise SbcImportError(f"{path.name} is not a PDF")

    target = cache_path(url, year)
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(body).hexdigest():
        archive(url, year)    # the file it replaces is kept (ADR 0016)
    save(body, target)
    with get_session() as session:
        stored = session.execute(
            select(SbcDocument.status, SbcDocument.sha256)
            .where(SbcDocument.url == url, SbcDocument.plan_year == year)
        ).first()
    status = ingest_document(url, year, stored, acquisition="manual")
    logger.info("sbc imported by hand: %s -> %s", target.name, status)
    return status


def _file_names(url: str) -> set[str]:
    """The names a browser may save this link's PDF under: the path's last
    segment, and any query value naming a PDF (e.g. `?fileName=x.pdf`)."""
    parts = urlsplit(url)
    names = {PurePosixPath(unquote(parts.path)).name}
    names.update(PurePosixPath(value).name for _, value in parse_qsl(parts.query)
                 if value.lower().endswith(".pdf"))
    return names


def import_folder(folder: Path, year: int) -> dict[str, str]:
    """Import every PDF in `folder` whose name is the file name of exactly one manual-only link.

    Returns each file's outcome: a status, or why it was not imported.
    """
    linked = _linked(year)
    by_name: dict[str, list[str]] = defaultdict(list)
    for url in linked:
        if host_access(url) == "manual":
            for name in _file_names(url):
                by_name[name].append(url)
    outcomes = {}
    for path in sorted(folder.glob("*.pdf")):
        urls = by_name.get(path.name, [])
        if len(urls) != 1:
            outcomes[path.name] = ("not imported: no manual-only link ends in this file name" if not urls
                                   else f"not imported: {len(urls)} links end in this file name; use FILE= and URL=")
            continue
        try:
            outcomes[path.name] = import_file(path, urls[0], year, linked)
        except SbcImportError as exc:
            outcomes[path.name] = f"not imported: {exc}"
    return outcomes


def _path(raw: str) -> Path:
    """A path as typed; `~` is expanded here because make passes it quoted."""
    return Path(raw).expanduser()


def parse_args(args):
    parser = argparse.ArgumentParser(description="Import SBC PDFs downloaded by hand.")
    parser.add_argument("--year", type=int, required=True, help="Plan year, e.g. 2026")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=_path, help="One downloaded PDF; needs --url")
    source.add_argument("--dir", type=_path, help="A folder of downloaded PDFs, matched to links by file name")
    parser.add_argument("--url", help="The plan's SBC link (from the manifest) that --file is the document behind")
    parsed = parser.parse_args(args)
    if parsed.file and not parsed.url:
        parser.error("--file needs --url")
    if parsed.dir and parsed.url:
        parser.error("--url goes with --file, not --dir")
    return parsed


def main(args=sys.argv[1:]) -> None:
    parsed = parse_args(args)
    if parsed.file:
        try:
            print(f"{parsed.file.name}: {import_file(parsed.file, parsed.url, parsed.year)}")
        except SbcImportError as exc:
            sys.exit(f"Not imported: {exc}")
        return
    if not parsed.dir.is_dir():
        sys.exit(f"{parsed.dir} is not a folder")
    outcomes = import_folder(parsed.dir, parsed.year)
    if not outcomes:
        sys.exit(f"No PDFs in {parsed.dir}")
    for name, outcome in outcomes.items():
        print(f"{name}: {outcome}")


if __name__ == "__main__":
    from src.core.logging import setup_logging

    setup_logging()
    main()
