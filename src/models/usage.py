import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base


class LlmUsage(Base):
    """Tokens a user has spent on generation, per UTC day.

    Flask-Limiter caps how many requests arrive, not how much each one costs,
    so a request within the rate limit can still be an expensive one. This is
    what the daily budget is checked against.
    """

    __tablename__ = "llm_usage"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_llm_usage_user_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
