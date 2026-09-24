from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.db import Base

# The one index there is. A second would be a second row, not a second table.
BM25_INDEX = "bm25"


class SearchIndex(Base):
    """A built search index, stored beside the chunks it indexes (ADR 0021).

    One row per index; `bm25` is the only one today. It lives here rather than
    on disk because the request path needs it and the app has to be able to
    run somewhere that has no `data/` directory. It is derived data: rebuilt
    from `chunks` whenever they change, never authored.
    """

    __tablename__ = "search_indexes"

    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
