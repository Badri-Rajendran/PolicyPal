"""create message_sources table

Revision ID: 98dcebd2ed1b
Revises: b9a94c6a97ad
Create Date: 2026-09-13 21:43:51.919998+00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '98dcebd2ed1b'
down_revision: str | Sequence[str] | None = 'b9a94c6a97ad'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "message_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # No FK to chunks: `make ingest` rebuilds that table wholesale, which
        # would cascade away every citation ever recorded (ADR 0007).
        sa.Column("chunk_id", sa.String(255), nullable=False),
        sa.Column("source", sa.String(300), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
    )
    op.create_index("ix_message_sources_message_id", "message_sources", ["message_id"])


def downgrade() -> None:
    op.drop_index("ix_message_sources_message_id", table_name="message_sources")
    op.drop_table("message_sources")
