"""add sbc_status to message_plans

Revision ID: b5a2418faad3
Revises: 89d744f9f2e0
Create Date: 2026-09-19 20:30:23.620507+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5a2418faad3"
down_revision: str | Sequence[str] | None = "89d744f9f2e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no backfill: a card saved before this was recorded says nothing (ADR 0017).
    op.add_column("message_plans", sa.Column("sbc_status", sa.String(length=16), nullable=True))
    op.create_check_constraint(
        "ck_message_plans_sbc_status",
        "message_plans",
        "sbc_status IS NULL OR sbc_status IN ('no_link', 'not_read', 'ok', 'blocked', 'http_error', "
        "'not_pdf', 'too_large', 'wrong_year', 'unparseable')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_message_plans_sbc_status", "message_plans", type_="check")
    op.drop_column("message_plans", "sbc_status")
