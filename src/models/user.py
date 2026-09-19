import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.db import Base

if TYPE_CHECKING:
    from src.models.chat import Thread


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # The plan-search profile (ADR 0012). Nullable only for accounts created
    # before it existed; signup requires it. Date of birth rather than age,
    # because an age goes stale and premiums rise with it. Personal data:
    # served only to its owner, never logged, never sent to the LLM.
    zip_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    county_fips: Mapped[str | None] = mapped_column(String(5), nullable=True)
    county_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)

    threads: Mapped[list["Thread"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def profile_complete(self) -> bool:
        return None not in (self.zip_code, self.date_of_birth, self.county_fips)
