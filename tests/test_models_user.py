import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.models.user import User


def test_user_defaults(session):
    user = User(email="alice@example.com", password_hash="hashed")
    session.add(user)
    session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert isinstance(user.created_at, datetime)
    assert user.is_active is True


def test_duplicate_email_rejected(session):
    session.add(User(email="bob@example.com", password_hash="hashed"))
    session.commit()

    session.add(User(email="bob@example.com", password_hash="other"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_email_required(session):
    session.add(User(password_hash="hashed"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_password_hash_required(session):
    session.add(User(email="carol@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()
