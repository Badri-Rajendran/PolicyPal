import uuid

from flask import g, request
from flask_jwt_extended import get_jwt_identity
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from src.core.db import SessionLocal
from src.models.user import User


class ValidationFailedError(Exception):
    """Raised when the request body fails schema validation. Never carries raw input."""

    def __init__(self, errors: list[dict]):
        self.errors = errors


class TokenBudgetExhaustedError(Exception):
    """Raised when a user has spent their daily generation budget (429)."""

    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class InvalidSessionError(Exception):
    """Raised when a signed token names no usable account (401). Carries no detail."""


def get_db() -> Session:
    """One SQLAlchemy session per request, reused across the request via flask.g."""
    if "db" not in g:
        g.db = SessionLocal()
    return g.db


def close_db(_exception: BaseException | None = None) -> None:
    db: Session | None = g.pop("db", None)
    if db is None:
        return

    if _exception is None:
        db.commit()
    else:
        db.rollback()
    db.close()


def get_current_user() -> User:
    """The authenticated user for this request. Call only inside a @jwt_required() view.

    A token can be signed and unexpired and still name nobody: its subject may
    not be one of our IDs, or the account may have been deleted since. Callers
    dereference the result, so returning None here became a 500 where the
    honest answer is 401 — the session is no good, sign in again.
    """
    db = get_db()
    try:
        user_id = uuid.UUID(get_jwt_identity())
    except (TypeError, ValueError) as exc:
        raise InvalidSessionError from exc

    user = db.get(User, user_id)
    if user is None:
        raise InvalidSessionError
    return user


def parse_body[T: BaseModel](schema: type[T]) -> T:
    """Validate the JSON request body against schema, or raise ValidationFailedError (422)."""
    try:
        return schema.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        errors = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationFailedError(errors) from exc
