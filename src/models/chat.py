import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.db import Base
from src.models.sbc import PLAN_SBC_STATUSES

if TYPE_CHECKING:
    from src.models.user import User


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (Index("ix_threads_user_id_updated_at", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        Index("ix_messages_thread_id_created_at", "thread_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    thread: Mapped["Thread"] = relationship(back_populates="messages")
    sources: Mapped[list["MessageSource"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="MessageSource.relevance.desc()"
    )
    plans: Mapped[list["MessagePlan"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="MessagePlan.position"
    )


class MessageSource(Base):
    """What an answer was grounded in, as it stood when the answer was given.

    `chunk_id` is deliberately not a foreign key: `make ingest` rebuilds the
    chunks table wholesale, which would either block re-ingestion or cascade
    away every citation ever recorded (ADR 0007).
    """

    __tablename__ = "message_sources"
    __table_args__ = (Index("ix_message_sources_message_id", "message_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(300), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)

    message: Mapped["Message"] = relationship(back_populates="sources")


class MessagePlan(Base):
    """A plan an answer showed, as it was shown (ADR 0011).

    A snapshot, not a pointer into the catalog: the premium was priced live
    for one age and cannot be recomputed without it, and a re-ingest or a new
    plan year changes the catalog underneath. So `(hios_plan_id, plan_year)`
    are plain columns, with no foreign key to `plans`, for ADR 0007's reason:
    a catalog refresh must neither be blocked by history nor cascade it away.

    `premium_age` is personal data, kept because a card without it misstates
    whose premium it shows. The ZIP code is never stored; the county is.
    """

    __tablename__ = "message_plans"
    __table_args__ = (
        # message_id leads, so this index also serves loading a message's plans.
        UniqueConstraint("message_id", "position", name="uq_message_plans_message_id_position"),
        CheckConstraint(f"sbc_status IS NULL OR sbc_status IN {PLAN_SBC_STATUSES}",
                        name="ck_message_plans_sbc_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    hios_plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    issuer: Mapped[str] = mapped_column(String(300), nullable=False)
    metal_level: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Null when CMS gave no live price; premium_reference (age 27) is then the only figure.
    monthly_premium: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    premium_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    premium_reference: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    deductible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    drug_deductible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    out_of_pocket_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    hsa_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    quality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    benefits_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether its Summary of Benefits could be read when shown (ADR 0017).
    # Null on cards saved before this was recorded.
    sbc_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    message: Mapped["Message"] = relationship(back_populates="plans")
