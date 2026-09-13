import pytest
from sqlalchemy.orm import Session

from src.api.limiter import limiter
from src.api.main import create_app
from src.core.db import engine


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True)
    limiter.reset()
    return application


@pytest.fixture
def client(app, monkeypatch):
    """A test client whose requests all share one rolled-back transaction.

    Every API request opens its own SQLAlchemy Session (see src.api.deps.get_db),
    so we monkeypatch SessionLocal to bind each of those sessions to the same
    connection/SAVEPOINT used by the `session` fixture below — this keeps API
    tests from writing to the real database while still letting requests within
    one test see each other's committed data.
    """
    connection = engine.connect()
    transaction = connection.begin()

    def make_session():
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    monkeypatch.setattr("src.api.deps.SessionLocal", make_session)

    try:
        yield app.test_client()
    finally:
        transaction.rollback()
        connection.close()


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
