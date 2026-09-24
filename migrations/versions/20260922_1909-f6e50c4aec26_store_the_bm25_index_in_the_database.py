"""Store the BM25 index in the database (ADR 0021)

One row per built index. It moves off local disk so the request path does
not need a `data/` directory, and so the index travels with the chunks it
indexes. Derived data: `make build-index` rebuilds it from `chunks`.

Revision ID: f6e50c4aec26
Revises: c4e91a7d6b28
Create Date: 2026-09-22 19:09:02.890934+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6e50c4aec26"
down_revision: str | Sequence[str] | None = "c4e91a7d6b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_indexes",
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("chunks", sa.Integer(), nullable=False),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name"),
    )


def downgrade() -> None:
    op.drop_table("search_indexes")
