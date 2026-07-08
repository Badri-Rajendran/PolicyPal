"""widen chunk_id column to 255

Revision ID: 2a96871b8cf3
Revises: c0fd2506b939
Create Date: 2026-07-03 17:45:28.186687+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a96871b8cf3'
down_revision: Union[str, Sequence[str], None] = 'c0fd2506b939'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "chunks",
        "chunk_id",
        existing_type=sa.String(50),
        type_=sa.String(255),
        existing_nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "chunks",
        "chunk_id",
        existing_type=sa.String(255),
        type_=sa.String(50),
        existing_nullable=False
    )
