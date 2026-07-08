"""create chunks table

Revision ID: 4875ce290d0d
Revises: 
Create Date: 2026-06-30 23:44:14.499279+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from src.policypal.config import settings


# revision identifiers, used by Alembic.
revision: str = '4875ce290d0d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. enable pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source", sa.String(300), index=True, nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dim), nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("chunks")
