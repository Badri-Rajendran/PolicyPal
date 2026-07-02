"""Create column chunk_id in Chunks table

Revision ID: c0fd2506b939
Revises: 4875ce290d0d
Create Date: 2026-07-03 17:21:52.458106+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0fd2506b939'
down_revision: Union[str, Sequence[str], None] = '4875ce290d0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("chunks", sa.Column("chunk_id", sa.String(50), nullable=False, index=True))
    op.create_unique_constraint("uq_chunks_chunk_id", "chunks", ["chunk_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_chunks_chunk_id", "chunks", type_="unique")
    op.drop_column("chunks", "chunk_id")
