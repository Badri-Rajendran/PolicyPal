"""Whether a plan's Summary of Benefits and Coverage can be read here, and why not (ADR 0017).

A plan reaches its document through `benefits_url` and its year, so the
status is an outer join: no link, a link never read, or the document's own
status. Reasons are written here, never taken from the stored `detail`.
"""
from sqlalchemy import and_, case

from src.models.plan import Plan
from src.models.sbc import SbcDocument

# A document whose text is stored and searchable. `partial` is read, but the
# federal template's questions or chart are not all in it, so an answer that
# cannot find a term must not conclude the plan lacks it.
READ_STATUSES = ("ok", "partial")

REASONS = {
    "no_link": "HealthCare.gov lists no Summary of Benefits and Coverage for this plan",
    "not_read": "its Summary of Benefits and Coverage hasn't been loaded here yet",
    "partial": "only part of its Summary of Benefits could be read: the costs chart is not all there",
    "blocked": "the insurer's website doesn't allow automated downloads",
    "http_error": "the insurer's link didn't return the document",
    "not_pdf": "the insurer's link returned a web page, not the document",
    "too_large": "the insurer's file is too large to be a Summary of Benefits and Coverage",
    "wrong_year": "the insurer's document is for a different plan year",
    "unparseable": "the document's text couldn't be read",
}


def sbc_document_join():
    """The ON clause from a plan to its document: the same link, the same year."""
    return and_(SbcDocument.url == Plan.benefits_url, SbcDocument.plan_year == Plan.plan_year)


def plan_sbc_status():
    """The plan's status, for a query that outer-joins SbcDocument on `sbc_document_join()`."""
    return case(
        (Plan.benefits_url.is_(None), "no_link"),
        (SbcDocument.id.is_(None), "not_read"),
        else_=SbcDocument.status,
    )


def missing_reason(status: str | None) -> str | None:
    """Why the plan's document can't be read here, in plain words; None when it can."""
    return REASONS.get(status) if status != "ok" else None
