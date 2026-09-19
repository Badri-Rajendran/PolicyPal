import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base

SBC_STATUSES = ("ok", "blocked", "http_error", "not_pdf", "too_large", "wrong_year", "unparseable")


class SbcDocument(Base):
    """One Summary of Benefits and Coverage PDF, as fetched for a plan year (ADR 0013).

    Plans reach it through `plans.benefits_url` and `plans.plan_year`, with no
    foreign key: several plans can share one document, and a plan re-sync must
    not have to know about it. The year is part of the key because issuers
    reuse a URL every year with new contents.

    Every attempt is recorded, not only successes, so a later run retries
    what failed and the ingest report can name it.
    """

    __tablename__ = "sbc_documents"
    __table_args__ = (
        UniqueConstraint("url", "plan_year", name="uq_sbc_documents_url_plan_year"),
        CheckConstraint(f"status IN {SBC_STATUSES}", name="ck_sbc_documents_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Why a fetch or parse failed, in a few words. Never a response body.
    detail: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The plan name printed on the SBC, which can differ from the catalog's.
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SbcChunk(Base):
    """One section of an SBC, as text a person could read (ADR 0014).

    Kept apart from `chunks` on purpose: general search must never see one
    plan's numbers, and a separate table makes that true without a filter
    every query has to remember. No embedding — a plan's chunks are few
    enough to rerank them all.
    """

    __tablename__ = "sbc_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sbc_documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    section: Mapped[str] = mapped_column(String(100), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
