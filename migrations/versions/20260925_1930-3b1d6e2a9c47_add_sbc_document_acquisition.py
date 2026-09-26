"""add sbc_documents.acquisition

Revision ID: 3b1d6e2a9c47
Revises: 15bb18a57fac
Create Date: 2026-09-25 19:30:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b1d6e2a9c47"
down_revision: str | Sequence[str] | None = "15bb18a57fac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every document stored so far was fetched by the crawler (ADR 0026).
    op.add_column("sbc_documents", sa.Column("acquisition", sa.String(length=8), server_default="crawl",
                                             nullable=False))
    op.create_check_constraint("ck_sbc_documents_acquisition", "sbc_documents",
                               "acquisition IN ('crawl', 'manual')")


def downgrade() -> None:
    op.drop_constraint("ck_sbc_documents_acquisition", "sbc_documents", type_="check")
    op.drop_column("sbc_documents", "acquisition")
