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
    """The authenticated user for this request. Call only inside a @jwt_required() view."""
    db = get_db()
    user_id = uuid.UUID(get_jwt_identity())
    return db.get(User, user_id)


def parse_body[T: BaseModel](schema: type[T]) -> T:
    """Validate the JSON request body against schema, or raise ValidationFailedError (422)."""
    try:
        return schema.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        errors = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        raise ValidationFailedError(errors) from exc
