"""add validators to sbc_documents

Revision ID: 7f4d9f435dd4
Revises: b5a2418faad3
Create Date: 2026-09-19 22:06:03.271828+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7f4d9f435dd4"
down_revision: str | Sequence[str] | None = "b5a2418faad3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sbc_documents", sa.Column("etag", sa.String(length=200), nullable=True))
    op.add_column("sbc_documents", sa.Column("last_modified", sa.String(length=64), nullable=True))
    op.add_column("sbc_documents", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
    # Every stored document was last checked when it was fetched (ADR 0019).
    op.execute("UPDATE sbc_documents SET checked_at = fetched_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sbc_documents", "checked_at")
    op.drop_column("sbc_documents", "last_modified")
    op.drop_column("sbc_documents", "etag")
