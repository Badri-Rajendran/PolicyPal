from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text

from sqlalchemy.orm import Mapped, mapped_column

from src.policypal.config import settings

from src.core.db import Base

class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(300), index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))