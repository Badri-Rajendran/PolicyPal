import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.models.usage import LlmUsage
from src.policypal.config import settings


def _today() -> date:
    return datetime.now(UTC).date()


def tokens_used_today(db: Session, user_id: uuid.UUID) -> int:
    stmt = select(LlmUsage.tokens_used).where(
        LlmUsage.user_id == user_id, LlmUsage.usage_date == _today()
    )
    return db.execute(stmt).scalar() or 0


def budget_exhausted(db: Session, user_id: uuid.UUID) -> bool:
    return tokens_used_today(db, user_id) >= settings.llm_daily_token_budget


def record_tokens(db: Session, user_id: uuid.UUID, tokens: int) -> None:
    """Add to today's total, creating the row if this is the day's first call.

    Upserted rather than read-modify-written: two concurrent requests reading
    the same total before either writes would otherwise lose one increment,
    and an undercounted budget is one that doesn't hold.
    """
    if tokens <= 0:
        return

    stmt = insert(LlmUsage).values(user_id=user_id, usage_date=_today(), tokens_used=tokens)
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_llm_usage_user_date",
            set_={"tokens_used": LlmUsage.tokens_used + stmt.excluded.tokens_used},
        )
    )


def seconds_until_budget_resets() -> int:
    """Until the next UTC midnight, for the Retry-After header."""
    now = datetime.now(UTC)
    midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC)
    return int((midnight.timestamp() + 86_400) - now.timestamp())
