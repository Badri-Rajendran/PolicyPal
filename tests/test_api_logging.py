"""The API process configures logging like every other entry point.

It did not, and the cost was invisible: the root logger kept Python's default
of WARNING with no handler, so nothing the request path logged reached
`logs/backend/app.log`, and the third-party levels that keep the CMS api key
and a user's ZIP out of the log were never installed.
"""
import logging
from logging.handlers import RotatingFileHandler

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from src.core import logging as app_logging
from src.core.db import engine


def test_creating_the_app_installs_the_file_handler(app):
    root = logging.getLogger()

    assert any(isinstance(handler, RotatingFileHandler) for handler in root.handlers)


def test_the_request_path_can_log_at_info(app):
    """The default root level of WARNING discarded every logger.info in a request."""
    assert logging.getLogger("src.services.generation").isEnabledFor(logging.INFO)


def test_the_libraries_that_would_log_secrets_stay_at_warning(app):
    """urllib3 logs the CMS URL with its ?apikey=; httpx and openai log the prompt."""
    for name in ("urllib3", "httpx", "openai"):
        assert logging.getLogger(name).level == logging.WARNING


def test_a_database_error_leaves_out_the_values_it_was_given():
    """SQLAlchemy's error text, which is logged, carries the bound values by
    default: an email, a question or an answer. (Postgres's own message can
    still quote a value it failed on; this error doesn't, so only SQLAlchemy's
    part is tested.)"""
    with engine.connect() as connection, pytest.raises(DBAPIError) as caught:
        connection.execute(text("SELECT :value, 1 / 0"), {"value": "someone@example.com"})

    assert "someone@example.com" not in str(caught.value)
    assert "hidden due to hide_parameters" in str(caught.value)


@pytest.fixture
def production(monkeypatch):
    monkeypatch.setattr(app_logging.settings, "environment", "production")
    yield
    app_logging.setup_logging()   # put the development configuration back


def _streams(root):
    return [h for h in root.handlers if type(h) is logging.StreamHandler]


def test_production_also_logs_to_stdout(production):
    """A container's filesystem is ephemeral and unread; the platform collects stdout."""
    app_logging.setup_logging()

    assert _streams(logging.getLogger())


def test_development_logs_only_to_the_file(app):
    """Otherwise an ingestion run's log lines interleave with its own progress output."""
    assert not _streams(logging.getLogger())
