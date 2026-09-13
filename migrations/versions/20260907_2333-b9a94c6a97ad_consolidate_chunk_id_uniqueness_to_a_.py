"""consolidate chunk_id uniqueness to a single index

Revision ID: b9a94c6a97ad
Revises: 09b53f758de3
Create Date: 2026-09-07 23:33:28.650019+00:00

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b9a94c6a97ad'
down_revision: str | Sequence[str] | None = '09b53f758de3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema.

    chunks.chunk_id has carried two redundant uniqueness objects since it was
    added: a plain index (from `index=True`) and a separate unique
    constraint, backed by its own implicit index. The ORM model only ever
    asked for one unique index. Drop both and replace them with the single
    unique index the model expects.
    """
    op.drop_constraint("uq_chunks_chunk_id", "chunks", type_="unique")
    op.drop_index("ix_chunks_chunk_id", table_name="chunks")
    op.create_index("ix_chunks_chunk_id", "chunks", ["chunk_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunks_chunk_id", table_name="chunks")
    op.create_index("ix_chunks_chunk_id", "chunks", ["chunk_id"], unique=False)
    op.create_unique_constraint("uq_chunks_chunk_id", "chunks", ["chunk_id"])
