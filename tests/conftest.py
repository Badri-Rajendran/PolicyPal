import pytest
from sqlalchemy.orm import Session

from src.core.db import engine


@pytest.fixture
def session():
    """A DB session bound to a transaction that is rolled back after each test.

    Uses a SAVEPOINT for the session's own commits so a test can call
    session.commit() (e.g. to trigger a constraint) without ending the
    outer transaction we roll back at teardown.
    """
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        yield db
    finally:
        db.close()
        transaction.rollback()
        connection.close()
