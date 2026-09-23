"""The API process configures logging like every other entry point.

It did not, and the cost was invisible: the root logger kept Python's default
of WARNING with no handler, so nothing the request path logged reached
`logs/backend/app.log`, and the third-party levels that keep the CMS api key
and a user's ZIP out of the log were never installed.
"""
import logging
from logging.handlers import RotatingFileHandler


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
