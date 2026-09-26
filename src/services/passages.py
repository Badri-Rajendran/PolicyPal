"""Cited passages, as the Sources panel shows them (ADR 0027).

A quote is brief (ADR 0013: SBC text is quoted, never redistributed) and is
the part of the passage most like the answer that cited it. Every field is
derived here, by the server, never taken from model output.
"""
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.urls import unsafe_reason
from src.ingestion.sources.registry import registered
from src.models.chunk import Chunk
from src.models.sbc import SbcChunk, SbcDocument

EXCERPT_CHARS = 300
_SBC_DOCUMENT = "Summary of Benefits and Coverage"
_SBC_SEPARATOR = " - Summary of Benefits - "      # plan_coverage.source_label
_SBC_YEAR = re.compile(r"^sbc_(\d{4})_")           # ingest's chunk ids: sbc_{year}_{key}_s.._c..
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "your", "with", "this", "that", "from", "have", "has", "was",
    "were", "will", "can", "its", "any", "all", "per", "may", "out",
})


@dataclass(frozen=True)
class Passage:
    kind: str                 # sbc | wikipedia | healthcare_gov | other
    title: str
    document: str | None
    section: str | None
    quote: str | None
    status: str               # ok | unverified | changed | missing
    url: str | None
    license: dict | None      # {"name", "url"}


def content_hash(text: str) -> str:
    """The passage text's fingerprint, stored with each citation."""
    return hashlib.sha256(text.encode()).hexdigest()


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if (len(w) >= 3 or w.isdigit()) and w not in _STOP_WORDS}


def _segments(text: str) -> list[str]:
    """Lines, then sentences within a line."""
    return [s.strip() for line in text.splitlines() for s in _SENTENCE_END.split(line) if s.strip()]


def excerpt(passage: str, answer_text: str, limit: int = EXCERPT_CHARS) -> str:
    """At most `limit` characters of `passage`, starting where it best matches the answer.

    The best segment shares the most distinct words with the answer (ties go
    to the earlier one); the segments after it follow while they fit. `… `
    and ` …` mark text left out before and after.
    """
    text = passage.strip()
    if len(text) <= limit:
        return text
    segments = _segments(text)
    wanted = _words(answer_text)
    best = max(range(len(segments)), key=lambda i: (len(_words(segments[i]) & wanted), -i))

    chosen: list[str] = []
    length = 0
    for segment in segments[best:]:
        added = len(segment) + (1 if chosen else 0)
        if length + added > limit:
            break
        chosen.append(segment)
        length += added

    if chosen:
        body = " ".join(chosen)
        reaches_end = best + len(chosen) == len(segments)
    else:
        # One segment longer than the limit: cut at the last space that fits.
        cut = segments[best][:limit]
        body = cut.rsplit(" ", 1)[0] if " " in cut else cut
        reaches_end = False
    return ("… " if best > 0 else "") + body + ("" if reaches_end else " …")


def _safe(url: str | None) -> str | None:
    """A link for the browser: https, to a public host name, or nothing."""
    return url if url and unsafe_reason(url) is None else None


def _stem(label: str) -> str:
    """The label without its last extension; SBC labels always end in .pdf, so a plan name's dot survives."""
    return label.rsplit(".", 1)[0] if "." in label else label


def _corpus_fields(label: str) -> tuple[str, str, str | None, str | None, dict | None]:
    """kind, title, document, url, license for a general-corpus label (ADR 0003)."""
    stem = _stem(label)
    if stem.startswith("wiki_"):
        title = stem.removeprefix("wiki_")
        entry = registered("wikipedia")
        license_ = {"name": entry.license, "url": entry.license_url} if entry else None
        url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
        return "wikipedia", title.replace("_", " "), "Wikipedia article", _safe(url), license_
    for prefix, document in (("hcg_glossary_", "HealthCare.gov glossary"), ("hcg_article_", "HealthCare.gov article")):
        if stem.startswith(prefix):
            # Public domain (17 U.S.C. § 105), and its page URL is not stored.
            return "healthcare_gov", stem.removeprefix(prefix).replace("_", " "), document, None, None
    return "other", stem, None, None, None


def _status(text: str | None, stored_hash: str | None) -> str:
    if text is None:
        return "missing"
    if stored_hash is None:
        return "unverified"
    return "ok" if content_hash(text) == stored_hash else "changed"


def _sbc_fields(db: Session, chunk_id: str, label: str) -> tuple[str | None, str, str, str | None, str | None]:
    """text, title, document, section, url for an SBC citation (ADR 0013)."""
    row = db.execute(
        select(SbcChunk.content, SbcDocument.url, SbcDocument.plan_year)
        .join(SbcDocument, SbcDocument.id == SbcChunk.document_id)
        .where(SbcChunk.chunk_id == chunk_id)
    ).first()
    plan, _, section = _stem(label).partition(_SBC_SEPARATOR)
    year = row.plan_year if row else (int(m.group(1)) if (m := _SBC_YEAR.match(chunk_id)) else None)
    document = f"{_SBC_DOCUMENT}, {year}" if year else _SBC_DOCUMENT
    return (row.content if row else None), plan.strip(), document, section.strip() or None, \
        _safe(row.url if row else None)


def passage_for(db: Session, chunk_id: str, label: str, stored_hash: str | None, answer_text: str) -> Passage:
    """The citation `label` → `chunk_id`, as it can be shown now.

    The quote is given only while the text can be trusted to be what was
    cited: `ok` (the hash matches) or `unverified` (an older citation, with
    no hash to check).
    """
    if chunk_id.startswith("sbc_"):
        text, title, document, section, url = _sbc_fields(db, chunk_id, label)
        kind, license_ = "sbc", None
    else:
        text = db.scalar(select(Chunk.content).where(Chunk.chunk_id == chunk_id))
        kind, title, document, url, license_ = _corpus_fields(label)
        section = None

    status = _status(text, stored_hash)
    shown = excerpt(text, answer_text) if text is not None and status in ("ok", "unverified") else None
    return Passage(kind, title, document, section, shown, status, url, license_)
