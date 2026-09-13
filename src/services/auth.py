import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from src.models.user import User


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def register_user(session: Session, email: str, password: str) -> User:
    """Create a new user account. Raises EmailAlreadyRegisteredError on a duplicate email."""
    existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegisteredError(f"{email} is already registered")

    user = User(email=email, password_hash=_hash_password(password))
    session.add(user)
    session.flush()
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    """Verify email/password. Raises InvalidCredentialsError if they don't match an active user."""
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if user is None or not user.is_active or not _verify_password(password, user.password_hash):
        raise InvalidCredentialsError("invalid email or password")

    return user
