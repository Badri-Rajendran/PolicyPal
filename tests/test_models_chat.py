import pytest
from sqlalchemy.exc import IntegrityError

from src.models.chat import Message, Thread
from src.models.user import User


def _make_user(session) -> User:
    user = User(email="dana@example.com", password_hash="hashed")
    session.add(user)
    session.commit()
    return user


def test_thread_messages_round_trip_in_order(session):
    user = _make_user(session)
    thread = Thread(user_id=user.id, title="Deductibles")
    session.add(thread)
    session.commit()

    session.add(Message(thread_id=thread.id, role="user", content="What is a deductible?"))
    session.commit()
    session.add(Message(thread_id=thread.id, role="assistant", content="It's the amount you pay first."))
    session.commit()

    session.refresh(thread)
    assert [m.role for m in thread.messages] == ["user", "assistant"]


def test_invalid_role_rejected(session):
    user = _make_user(session)
    thread = Thread(user_id=user.id)
    session.add(thread)
    session.commit()

    session.add(Message(thread_id=thread.id, role="system", content="not allowed"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_user_cascades_threads_and_messages(session):
    user = _make_user(session)
    thread = Thread(user_id=user.id)
    session.add(thread)
    session.commit()
    session.add(Message(thread_id=thread.id, role="user", content="hello"))
    session.commit()

    session.delete(user)
    session.commit()

    assert session.get(Thread, thread.id) is None
    assert session.query(Message).filter_by(thread_id=thread.id).first() is None


def test_message_requires_thread(session):
    session.add(Message(role="user", content="orphaned"))
    with pytest.raises(IntegrityError):
        session.commit()
