import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.db import Base


class Issuer(Base):
    """An insurance company selling on the Marketplace, as of one plan year.

    Keyed per plan year so a 2027 sync cannot rewrite the contact details a
    2026 plan points at. HIOS issuer ids are already state-scoped, so
    `(hios_issuer_id, plan_year)` is unique nationally.
    """

    __tablename__ = "issuers"
    __table_args__ = (
        UniqueConstraint("hios_issuer_id", "plan_year", name="uq_issuers_hios_issuer_id_plan_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hios_issuer_id: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    individual_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    toll_free: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Plan(Base):
    """One purchasable plan in the Marketplace catalog (ADR 0009).

    `premium_reference` is the unsubsidized premium for a single 27-year-old,
    CMS's own convention for comparing premiums. It is indicative, never a
    quote: the same plan costs roughly twice as much at 55.

    Money is `Numeric`, not `Float`: these values are compared in `WHERE`
    clauses, and a float cannot hold cents exactly. `metal_level` and
    `plan_type` carry no CHECK constraint because the vocabulary is CMS's,
    not ours — a new level would otherwise fail ingestion over valid data.
    """

    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("hios_plan_id", "plan_year", name="uq_plans_hios_plan_id_plan_year"),
        Index("ix_plans_plan_year_state_metal_level", "plan_year", "state", "metal_level"),
        Index("ix_plans_issuer_id", "issuer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("issuers.id", ondelete="CASCADE"), nullable=False
    )
    hios_plan_id: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    marketing_name: Mapped[str] = mapped_column(String(300), nullable=False)
    metal_level: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    premium_reference: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    hsa_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    has_national_network: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_standardized_plan: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # CMS reports an unrated plan as 0; stored as NULL so "lowest rated"
    # never means "not rated yet".
    quality_rating_global: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_rating_clinical: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_rating_enrollee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_rating_efficiency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_not_rated_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # benefits_url is the plan's Summary of Benefits and Coverage PDF.
    benefits_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    brochure_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    formulary_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    network_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PlanCounty(Base):
    """A county a plan can be bought in.

    Plans are sold per county, so without this a ZIP-level search could only
    narrow to the state and would return plans the caller cannot buy.
    """

    __tablename__ = "plan_counties"
    __table_args__ = (
        UniqueConstraint("plan_id", "countyfips", name="uq_plan_counties_plan_id_countyfips"),
        Index("ix_plan_counties_countyfips", "countyfips"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    countyfips: Mapped[str] = mapped_column(String(5), nullable=False)


class PlanCostShare(Base):
    """A deductible or out-of-pocket maximum, one row per variant.

    A plan has several: one per CSR variant, network tier and family split,
    and sometimes two that differ only by `cost_share_type` (a medical and a
    drug deductible), which is why the type is part of the unique key. Every
    key column is NOT NULL — Postgres treats NULLs as distinct, so one
    nullable key column would let every re-sync insert duplicates.

    The foreign key cascades, unlike `message_sources.chunk_id` (ADR 0007).
    That rule protects history from a corpus rebuild; these rows are current
    state from the same sync as their plan, and should leave with it.
    """

    __tablename__ = "plan_cost_shares"
    __table_args__ = (
        CheckConstraint("kind IN ('deductible', 'moop')", name="ck_plan_cost_shares_kind"),
        UniqueConstraint(
            "plan_id",
            "kind",
            "cost_share_type",
            "csr_variant",
            "network_tier",
            "family_cost",
            name="uq_plan_cost_shares_plan_kind_type_csr_tier_family",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    cost_share_type: Mapped[str] = mapped_column(String(200), nullable=False)
    csr_variant: Mapped[str] = mapped_column(String(64), nullable=False)
    network_tier: Mapped[str] = mapped_column(String(64), nullable=False)
    family_cost: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class ZipCounty(Base):
    """A county a ZIP code lies in, for one plan year.

    Plans are sold per county, but people know their ZIP, and 28% of ZIPs span
    more than one county (74103 is in Tulsa and Osage). Holds every
    jurisdiction CMS lists, not only the ingested states, so a ZIP in a state
    that runs its own exchange can be told apart from a mistyped one.
    """

    __tablename__ = "zip_counties"
    __table_args__ = (
        # ZIP first, so the constraint's index also serves the lookup.
        UniqueConstraint("zipcode", "plan_year", "countyfips", name="uq_zip_counties_zipcode_plan_year_countyfips"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zipcode: Mapped[str] = mapped_column(String(5), nullable=False)
    plan_year: Mapped[int] = mapped_column(Integer, nullable=False)
    countyfips: Mapped[str] = mapped_column(String(5), nullable=False)
    county_name: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
