"""Add the filed-rate catalog: California plans from CMS's state-based exchange PUF (ADR 0024)

`plans.catalog_source` says which pipeline wrote a plan. `plan_counties.zipcodes`
limits a plan to some ZIPs of a county. `rating_areas`, `plan_rates` and
`catalog_loads` hold a filed-rate state's rating geography, premiums and load
history. The API path writes none of these, so its rows are unchanged.

Revision ID: 15bb18a57fac
Revises: f6e50c4aec26
Create Date: 2026-09-24 23:14:29.605722+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "15bb18a57fac"
down_revision: str | Sequence[str] | None = "f6e50c4aec26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans", sa.Column("catalog_source", sa.String(length=16), server_default="cms_api", nullable=False)
    )
    op.create_check_constraint("ck_plans_catalog_source", "plans", "catalog_source IN ('cms_api', 'ca_sbe_puf')")
    op.add_column("plan_counties", sa.Column("zipcodes", postgresql.ARRAY(sa.String(length=5)), nullable=True))
    op.create_table(
        "rating_areas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("plan_year", sa.Integer(), nullable=False),
        sa.Column("countyfips", sa.String(length=5), nullable=False),
        sa.Column("zip3", sa.String(length=3), server_default="", nullable=False),
        sa.Column("rating_area", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_year", "countyfips", "zip3", name="uq_rating_areas_plan_year_countyfips_zip3"),
    )
    op.create_table(
        "plan_rates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("rating_area", sa.SmallInteger(), nullable=False),
        sa.Column("age", sa.SmallInteger(), nullable=False),
        sa.Column("individual_rate", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.CheckConstraint("age BETWEEN 14 AND 64", name="ck_plan_rates_age"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "rating_area", "age", name="uq_plan_rates_plan_id_rating_area_age"),
    )
    op.create_table(
        "catalog_loads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("plan_year", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_label", sa.String(length=32), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("plans", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("catalog_loads")
    op.drop_table("plan_rates")
    op.drop_table("rating_areas")
    op.drop_column("plan_counties", "zipcodes")
    op.drop_constraint("ck_plans_catalog_source", "plans", type_="check")
    op.drop_column("plans", "catalog_source")
