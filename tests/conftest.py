import pytest
from sqlalchemy.orm import Session

from src.api.limiter import limiter
from src.api.main import create_app
from src.core.db import engine
from tests.helpers import seed_zip_counties


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
    seed_zip_counties(make_session())

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


_SBC_HOST = """
[[source]]
id = "{id}"
name = "{id}"
publisher = "An insurer"
scope_urls = ["{prefix}"]
kind = "sbc_host"
jurisdiction = "{state}"
license = "All rights reserved"
license_url = "https://example.com/terms"
permission_status = "mandated_disclosure"
commercial_use = "review"
robots = "allowed"
robots_checked_on = 2026-09-26
access = "{access}"
verified_on = 2026-09-26
enabled = {enabled}
removal = "Disable it."
notes = ""
"""


@pytest.fixture
def sbc_hosts(monkeypatch, tmp_path):
    """The committed registry plus made-up carrier hosts (ADR 0026).

    Returns {id: URL prefix}: `crawl` and `manual` are enabled California
    hosts, `off` a disabled one, and `texas` an enabled host of another state.
    """
    from src.ingestion.sources import registry

    hosts = {
        "crawl": ("https://crawl.example.com/sbc/", "CA", "crawl", "true"),
        "manual": ("https://manual.example.com/sbc/", "CA", "manual", "true"),
        "off": ("https://off.example.com/sbc/", "CA", "crawl", "false"),
        "texas": ("https://texas.example.com/sbc/", "TX", "crawl", "true"),
    }
    path = tmp_path / "registry.toml"
    path.write_text("".join(_SBC_HOST.format(id=id_, prefix=prefix, state=state, access=access, enabled=enabled)
                            for id_, (prefix, state, access, enabled) in hosts.items()), encoding="utf-8")
    loaded = registry.load_registry() | registry.load_registry(path)
    monkeypatch.setattr(registry, "_committed", lambda: loaded)
    return {id_: prefix for id_, (prefix, *_) in hosts.items()}
