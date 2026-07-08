from ..policypal.config import settings
from collections.abc import Iterator

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    "ORM class for postgres"
    pass


@contextmanager
def get_session() -> Iterator[Session]:
    "This function is a Session Factory: Returns session for each get_session function call"
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()