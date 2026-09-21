"""add the partial sbc status

Revision ID: c4e91a7d6b28
Revises: 7f4d9f435dd4
Create Date: 2026-09-20 01:30:11.402913+00:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e91a7d6b28"
down_revision: str | Sequence[str] | None = "7f4d9f435dd4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A document that was read, but without all of the federal template's
# questions or its costs chart (ADR 0017).
OLD = ("ok", "blocked", "http_error", "not_pdf", "too_large", "wrong_year", "unparseable")
NEW = ("ok", "partial", *OLD[1:])


def _statuses(document: tuple[str, ...], plan: tuple[str, ...]) -> None:
    op.drop_constraint("ck_sbc_documents_status", "sbc_documents", type_="check")
    op.create_check_constraint("ck_sbc_documents_status", "sbc_documents", f"status IN {document}")
    op.drop_constraint("ck_message_plans_sbc_status", "message_plans", type_="check")
    op.create_check_constraint("ck_message_plans_sbc_status", "message_plans",
                               f"sbc_status IS NULL OR sbc_status IN {plan}")


def upgrade() -> None:
    _statuses(NEW, ("no_link", "not_read", *NEW))


def downgrade() -> None:
    # Nothing may claim to be fully read when it was not: a partial document
    # goes back to being unparseable, and the cards that showed it follow.
    op.execute("UPDATE sbc_documents SET status = 'unparseable' WHERE status = 'partial'")
    op.execute("UPDATE message_plans SET sbc_status = 'unparseable' WHERE sbc_status = 'partial'")
    _statuses(OLD, ("no_link", "not_read", *OLD))
