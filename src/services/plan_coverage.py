"""What one plan's SBC says about a question (ADR 0014).

A plan's document has about 25 sections, so every one is reranked against the
question and the best few returned, with no relevance gate: within one plan
the right section is nearly always there, and scores low only when the
question's words differ from the template's.
"""
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select

from src.core.logging import get_logger
from src.core.reranker import rerank
from src.models.plan import Issuer, Plan
from src.models.sbc import SbcChunk, SbcDocument

from .retrieval import RetrievedChunk
from .sbc_status import READ_STATUSES, plan_sbc_status, sbc_document_join

logger = get_logger(__name__)

PASSAGES_PER_PLAN = 4
# message_sources.source is String(300).
_MAX_LABEL = 300
_LABEL_SUFFIX = " - Summary of Benefits - {section}.pdf"

CoverageStatus = Literal["ok", "not_found", "no_document", "unavailable"]


@dataclass(frozen=True)
class PlanCoverage:
    plan_id: str
    status: CoverageStatus
    name: str | None = None
    issuer: str | None = None
    plan_year: int | None = None
    sbc_url: str | None = None
    passages: tuple[RetrievedChunk, ...] = ()
    # The precise status behind `status` (ADR 0017): "blocked", "not_read"…
    sbc_status: str | None = None


def coverage_for(session, plan_ids: list[str], question: str,
                 years: Mapping[str, int] | None = None) -> list[PlanCoverage]:
    """Each plan's most relevant SBC passages, in the order the IDs were given.

    A plan is read in the year it was shown (`years`), else the latest catalog
    year it has.
    """
    return [_coverage(session, plan_id, question, (years or {}).get(plan_id)) for plan_id in plan_ids]


def _coverage(session, plan_id: str, question: str, year: int | None) -> PlanCoverage:
    stmt = (
        select(Plan.marketing_name, Plan.plan_year, Plan.benefits_url, Issuer.name,
               SbcDocument.id, plan_sbc_status())
        .join(Issuer, Issuer.id == Plan.issuer_id)
        .outerjoin(SbcDocument, sbc_document_join())
        .where(Plan.hios_plan_id == plan_id)
        .order_by(Plan.plan_year.desc())
        .limit(1)
    )
    if year is not None:
        stmt = stmt.where(Plan.plan_year == year)
    row = session.execute(stmt).first()
    if row is None:
        return PlanCoverage(plan_id, "not_found")

    name, plan_year, url, issuer, document_id, sbc_status = row
    if sbc_status not in READ_STATUSES:
        status = "no_document" if sbc_status in ("no_link", "not_read") else "unavailable"
        return PlanCoverage(plan_id, status, name, issuer, plan_year, url, sbc_status=sbc_status)

    chunks = session.execute(
        select(SbcChunk.chunk_id, SbcChunk.section, SbcChunk.content)
        .where(SbcChunk.document_id == document_id)
    ).all()
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    ranked = rerank(question, [(chunk.chunk_id, chunk.content) for chunk in chunks], PASSAGES_PER_PLAN)
    passages = tuple(
        RetrievedChunk(
            chunk_id=chunk_id,
            content=by_id[chunk_id].content,
            source=source_label(name, by_id[chunk_id].section),
            score=1 / (1 + math.exp(-float(logit))),
        )
        for chunk_id, logit in ranked
    )
    # Scores are logged, not gated on (ADR 0014); never the question itself.
    logger.info("plan_coverage %s: %s", plan_id, [round(p.score, 3) for p in passages])
    return PlanCoverage(plan_id, "ok", name, issuer, plan_year, url, passages, sbc_status)


def source_label(plan_name: str, section: str) -> str:
    """The citation label: the plan, the document and the section.

    Ends in ".pdf" because the frontend strips a label's last extension, and a
    plan name's own dot ("Silver 2.0") must not be taken for one. The plan
    name gives way first when the whole would not fit the column.
    """
    suffix = _LABEL_SUFFIX.format(section=section)
    return plan_name.strip()[:_MAX_LABEL - len(suffix)] + suffix
