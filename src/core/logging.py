import json
import logging
import sys
from datetime import datetime, timezone
from logging.config import dictConfig
from pathlib import Path

from src.policypal.config import settings


class JsonFormatter(logging.Formatter):
    '''JSON output for production log.'''
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    '''Configure file-based logging.'''
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "app.log"

    is_prod = settings.environment == "production"

    dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%m-%d-%Y %H:%M:%S"
            },
            "json": {
                "()": "src.core.logging.JsonFormatter"
            }
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_file),
                "maxBytes": 10 * 1024 * 1024,
                "backupCount": 5,               # keep app.log + 5 rotated copies
                "encoding": "utf-8",
                "formatter": "json" if is_prod else "console"
            }
        },
        "root": {
            "level": settings.log_level,
            "handlers": ["file"]
        },
        "loggers": {
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": ["file"],
                "propagate": False
            }
        }
    })


def get_logger(name: str) -> logging.Logger:

    return logging.getLogger(name)