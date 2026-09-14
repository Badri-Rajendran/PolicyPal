import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.db import Base

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
