"""add message_sources.content_sha256

Revision ID: 9c1e4b7a2d10
Revises: 3b1d6e2a9c47
Create Date: 2026-09-26 12:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c1e4b7a2d10"
down_revision: str | Sequence[str] | None = "3b1d6e2a9c47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The passage text an answer used, hashed, so a rebuilt chunk that now says
    # something else is never shown as what was cited (ADR 0007, 0027). Older
    # citations stay NULL: "unverified".
    op.add_column("message_sources", sa.Column("content_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("message_sources", "content_sha256")
