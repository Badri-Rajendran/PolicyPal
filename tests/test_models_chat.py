import pytest
from sqlalchemy.exc import IntegrityError

from src.models.chat import Message, MessagePlan, Thread
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


def _card(message, sbc_status):
    return MessagePlan(message_id=message.id, position=1, hios_plan_id="11111TX0010001", plan_year=2026,
                       name="Plan", issuer="Issuer", metal_level="Silver", plan_type="HMO", hsa_eligible=False,
                       county_name="Anderson", state="TX", sbc_status=sbc_status)


def _answer(session):
    thread = Thread(user_id=_make_user(session).id)
    session.add(thread)
    session.commit()
    message = Message(thread_id=thread.id, role="assistant", content="Plans.")
    session.add(message)
    session.commit()
    return message


@pytest.mark.parametrize("sbc_status", [None, "ok", "no_link", "not_read", "blocked"])
def test_a_plan_card_records_a_known_sbc_status_or_none(session, sbc_status):
    """None is a card saved before the status was recorded (ADR 0017)."""
    message = _answer(session)
    session.add(_card(message, sbc_status))
    session.commit()

    assert session.get(MessagePlan, message.plans[0].id).sbc_status == sbc_status


def test_a_plan_card_rejects_an_unknown_sbc_status(session):
    session.add(_card(_answer(session), "readable"))
    with pytest.raises(IntegrityError):
        session.commit()
