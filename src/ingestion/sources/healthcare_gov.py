"""HealthCare.gov corpus source: authoritative consumer-facing guidance.

Wikipedia explains what insurance *is*; this explains what a policyholder
*does* — what a copay is versus coinsurance, how to appeal a denial, when a
Special Enrollment Period applies. A retrieval probe over the Wikipedia-only
corpus failed to answer 12 of 20 realistic consumer questions; every one of
those gaps is covered here. See ADR 0003.

Two collections, chunked differently because their shapes differ:

  glossary → one term is one chunk. Definitions are short and atomic, so
             splitting them would only sever a term from its definition.
  articles → recursive splitting, same strategy as Wikipedia prose.
"""
import datetime as dt
import json
import re

import requests
from tqdm import tqdm

from src.core.logging import get_logger
from src.policypal.config import settings

from ..chunking import make_chunk, make_chunk_id, make_recursive_splitter, sanitize_name
from ..constants import (
    HEALTHCARE_GOV_BASE_URL,
    HEALTHCARE_GOV_COLLECTIONS,
    HEALTHCARE_GOV_USER_AGENT,
    MARKDOWN,
    RAW,
)
from ..html_text import html_to_markdown
from .base import Source

logger = get_logger(__name__)

_REQUEST_TIMEOUT_SECONDS = 60

_YEAR_IN_TITLE_RE = re.compile(r"\b(20\d{2})\b")

# Marketplace content is dated. Keeping last year's is legitimate (tax content
# for the prior year is still filed during the current one); anything older
# describes rules that no longer apply, and answering a live question with it
# is worse than returning nothing.
_MAX_YEARS_STALE = 1


def _is_stale(title: str, today: dt.date | None = None) -> bool:
    """True if the title names a plan/tax year too old to still be accurate."""
    today = today or dt.datetime.now(tz=dt.UTC).date()
    years = [int(y) for y in _YEAR_IN_TITLE_RE.findall(title)]

    if not years:
        return False

    # A title naming a range ("2016 and 2017") is only stale if its most
    # recent year is stale.
    return max(years) < today.year - _MAX_YEARS_STALE


class HealthCareGovSource(Source):
    name = "healthcare_gov"

    def fetch(self) -> None:
        print("\n=== HealthCare.gov: downloading content collections ===")

        RAW.mkdir(parents=True, exist_ok=True)

        for collection, filename in HEALTHCARE_GOV_COLLECTIONS.items():
            out_path = RAW / filename

            if out_path.exists():
                print(f"  {collection}: already exists, skipping")
                continue

            url = f"{HEALTHCARE_GOV_BASE_URL}/{collection}.json"

            try:
                response = requests.get(
                    url,
                    headers={"User-Agent": HEALTHCARE_GOV_USER_AGENT},
                    timeout=_REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()

                # Parse before writing so a truncated or HTML error page never
                # lands on disk looking like a good download to the next run.
                payload = response.json()
                if collection not in payload:
                    raise ValueError(f"response has no {collection!r} key")

                out_path.write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )
                print(f"  {collection}: downloaded ({len(payload[collection])} entries)")

            except (requests.RequestException, ValueError) as e:
                # One failed collection must not abort the whole ingest; the
                # normalize phase reports what's missing.
                print(f"  {collection}: ERROR — {e}")
                logger.warning("healthcare.gov fetch failed for %s: %s", collection, e)

    def normalize(self) -> None:
        print("\n=== HealthCare.gov: converting to markdown ===")

        MARKDOWN.mkdir(parents=True, exist_ok=True)

        for collection in HEALTHCARE_GOV_COLLECTIONS:
            entries = self._load_raw(collection)

            if entries is None:
                print(f"  {collection}: raw file not found, skipping")
                continue

            written = skipped_stale = skipped_empty = 0

            for entry in tqdm(entries, desc=f"HealthCare.gov {collection}"):
                title = (entry.get("title") or "").strip()
                if not title:
                    skipped_empty += 1
                    continue

                if _is_stale(title):
                    skipped_stale += 1
                    continue

                body = html_to_markdown(entry.get("content") or "")
                if not body:
                    skipped_empty += 1
                    continue

                dst = MARKDOWN / self._markdown_name(collection, title)
                dst.write_text(f"# {title}\n\n{body}", encoding="utf-8")
                written += 1

            print(
                f"  {collection}: {written} written, "
                f"{skipped_stale} skipped as out-of-date, {skipped_empty} skipped as empty"
            )

    def chunk_documents(self) -> list[dict]:
        print("\n=== Chunking HealthCare.gov content ===")

        chunks: list[dict] = []

        glossary = self._chunk_glossary()
        print(f"  glossary: {len(glossary)} chunks")
        chunks.extend(glossary)

        articles = self._chunk_articles()
        print(f"  articles: {len(articles)} chunks")
        chunks.extend(articles)

        return chunks

    # Collection-specific chunking

    def _chunk_glossary(self) -> list[dict]:
        """One term, one chunk — a definition split in half answers nothing."""
        chunks = []

        for title, body, path in self._markdown_documents("glossary"):
            sanitized = sanitize_name(title)

            chunks.append(make_chunk(
                text=f"{title}: {body}",
                # The term is already the first thing in the text, so the
                # contextual prefix only needs to say what kind of document
                # this is and which corpus it came from.
                contextualized_text=f"Health insurance glossary\n{title}\n{body}",
                chunk_id=make_chunk_id(self.name, f"glossary_{sanitized}", 0),
                source_file=path.name,
                doc_type="healthcare_gov_glossary",
                title=title,
                section=title,
                chunk_index=0,
                is_abstract=True,
            ))

        return chunks

    def _chunk_articles(self) -> list[dict]:
        splitter = make_recursive_splitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        chunks = []

        for title, body, path in self._markdown_documents("article"):
            sanitized = sanitize_name(title)
            cur_section = title

            for c_idx, raw_text in enumerate(splitter.split_text(body)):
                chunk_text = raw_text.strip()
                if not chunk_text:
                    continue

                # Markdown headings survive normalize(), so the section a chunk
                # belongs to can be read directly rather than guessed at.
                heading = re.match(r"^#{1,6}\s+(.+)", chunk_text)
                if heading:
                    cur_section = heading.group(1).strip()

                contextualized_text = (
                    f"{title}\n{chunk_text}"
                    if cur_section == title
                    else f"{title}\n{cur_section}\n{chunk_text}"
                )

                chunks.append(make_chunk(
                    text=chunk_text,
                    contextualized_text=contextualized_text,
                    chunk_id=make_chunk_id(self.name, f"article_{sanitized}", c_idx),
                    source_file=path.name,
                    doc_type="healthcare_gov_article",
                    title=title,
                    section=cur_section,
                    chunk_index=c_idx,
                ))

        return chunks

    # Helpers

    @staticmethod
    def _markdown_name(collection: str, title: str) -> str:
        # "articles" -> "article" so the file prefix reads as one document.
        singular = collection.rstrip("s")
        return f"hcg_{singular}_{sanitize_name(title)}.md"

    @staticmethod
    def _load_raw(collection: str) -> list[dict] | None:
        path = RAW / HEALTHCARE_GOV_COLLECTIONS[collection]

        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get(collection, [])

    @staticmethod
    def _markdown_documents(singular: str):
        """Yield (title, body, path) for this source's markdown files."""
        for path in sorted(MARKDOWN.glob(f"hcg_{singular}_*.md")):
            text = path.read_text(encoding="utf-8")

            heading = re.match(r"^#\s+(.+)\n+", text)
            if not heading:
                logger.warning("skipping %s: no title heading", path.name)
                continue

            body = text[heading.end():].strip()
            if body:
                yield heading.group(1).strip(), body, path
