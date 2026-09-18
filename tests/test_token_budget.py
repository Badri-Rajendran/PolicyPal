"""The daily token budget (CLAUDE.md: cost limits, not just rate limits).

Flask-Limiter caps how many requests arrive; it says nothing about what each
one spends. These cover the budget that does.
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import openai

from src.models.usage import LlmUsage
from src.policypal.config import settings
from src.services.generation import Answer, _tokens_used
from src.services.usage import record_tokens, tokens_used_today


def _auth_headers(client, email):
    token = client.post(
        "/api/auth/register", json={"email": email, "password": "correct-horse-1"}
    ).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _thread(client, headers):
    return client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]


def _send(client, headers, thread_id, content="What is a deductible?"):
    return client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": content}, headers=headers
    )


@patch("src.api.routes.chat.token_usage", return_value=1_500)
@patch("src.api.routes.chat.answer_query", return_value=Answer("an answer", []))
def test_a_message_under_budget_is_answered(_query, _usage, client):
    headers = _auth_headers(client, "budget-ok@example.com")

    assert _send(client, headers, _thread(client, headers)).status_code == 201


@patch("src.api.routes.chat.token_usage", return_value=1_500)
@patch("src.api.routes.chat.answer_query", return_value=Answer("an answer", []))
def test_spending_the_budget_blocks_the_next_message(_query, _usage, client):
    headers = _auth_headers(client, "budget-out@example.com")
    thread_id = _thread(client, headers)

    with patch.object(settings, "llm_daily_token_budget", 1_000):
        assert _send(client, headers, thread_id).status_code == 201   # 1500 recorded
        blocked = _send(client, headers, thread_id)                   # over, refused

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert int(blocked.headers["Retry-After"]) > 0
    # The point of the check running before generation: a blocked message
    # must never reach the paid call. Without this, moving the check below
    # answer_query would still pass every other assertion here.
    assert _query.call_count == 1


@patch("src.api.routes.chat.token_usage", return_value=1_500)
@patch("src.api.routes.chat.answer_query", return_value=Answer("an answer", []))
def test_exhaustion_is_distinguishable_from_a_rate_limit(_query, _usage, client):
    """The UI has to tell "slow down" apart from "you're done until tomorrow"."""
    headers = _auth_headers(client, "budget-msg@example.com")
    thread_id = _thread(client, headers)

    with patch.object(settings, "llm_daily_token_budget", 1_000):
        _send(client, headers, thread_id)                      # spends 1500
        body = _send(client, headers, thread_id).get_json()    # refused

    assert body["error"] == "daily token budget exhausted"


@patch("src.api.routes.chat.token_usage", return_value=1_000)
@patch("src.api.routes.chat.answer_query", return_value=Answer("an answer", []))
def test_usage_accumulates_across_messages(_query, _usage, client):
    """Each message spends 1000 against a 2500 budget, so the fourth is refused.
    If usage did not accumulate, no message would ever be."""
    headers = _auth_headers(client, "budget-add@example.com")
    thread_id = _thread(client, headers)

    with patch.object(settings, "llm_daily_token_budget", 2_500):
        codes = [_send(client, headers, thread_id).status_code for _ in range(4)]

    assert codes == [201, 201, 201, 429]


@patch("src.api.routes.chat.token_usage", return_value=1_500)
@patch("src.api.routes.chat.answer_query", return_value=Answer("an answer", []))
def test_one_users_spend_does_not_block_another(_query, _usage, client):
    spender = _auth_headers(client, "budget-spender@example.com")
    other = _auth_headers(client, "budget-other@example.com")
    spender_thread = _thread(client, spender)
    other_thread = _thread(client, other)

    with patch.object(settings, "llm_daily_token_budget", 1_000):
        _send(client, spender, spender_thread)
        assert _send(client, spender, spender_thread).status_code == 429
        assert _send(client, other, other_thread).status_code == 201


@patch("src.api.routes.chat.record_tokens")
@patch("src.api.routes.chat.answer_query")
def test_a_reset_message_never_bills_the_previous_ones_spend(mock_query, mock_record, client):
    """token_usage() reads a ContextVar that outlives one request on a reused
    thread. Every other test here patches token_usage() directly and so
    cannot see this — reset_token_usage() could be deleted and they would
    still pass. This one lets the real counter run and bills a different
    amount each call, so a leaked total is distinguishable from a correctly
    reset one."""
    amounts = iter([1_000, 1_500])

    def _answer_and_bill(*_args, **_kwargs):
        _tokens_used.set(_tokens_used.get() + next(amounts))
        return "an answer", []

    mock_query.side_effect = _answer_and_bill
    headers = _auth_headers(client, "budget-reset@example.com")
    thread_id = _thread(client, headers)

    _send(client, headers, thread_id)
    _send(client, headers, thread_id)

    recorded = [call.args[2] for call in mock_record.call_args_list]
    assert recorded == [1_000, 1_500]  # not [1_000, 2_500]


@patch("src.api.routes.chat.token_usage", return_value=750)
@patch("src.api.routes.chat.answer_query")
def test_a_failed_generation_still_records_its_spend_and_keeps_the_message(_query, _usage, client):
    """A timeout after a billed call must not make that spend disappear, and
    must not lose the question the user already asked."""
    _query.side_effect = [openai.OpenAIError("boom"), ("an answer", [])]
    headers = _auth_headers(client, "budget-fail@example.com")
    thread_id = _thread(client, headers)

    with patch.object(settings, "llm_daily_token_budget", 700):
        failed = _send(client, headers, thread_id, content="Does this persist?")
        assert failed.status_code == 502
        assert failed.get_json() == {"error": "generation failed"}

        # The failed call already billed 750 against a 700 budget, so the
        # next message is blocked before it can spend anything more —
        # proof the partial spend was actually recorded, not just logged.
        blocked = _send(client, headers, thread_id)

    assert blocked.status_code == 429

    messages = client.get(
        f"/api/chat/threads/{thread_id}/messages", headers=headers
    ).get_json()
    assert len(messages) == 1
    assert messages[0]["content"] == "Does this persist?"
    assert messages[0]["role"] == "user"


def test_yesterdays_usage_does_not_count_against_today(session):
    from src.models.user import User

    user = User(email="budget-yesterday@example.com", password_hash="x")
    session.add(user)
    session.flush()

    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    session.add(LlmUsage(user_id=user.id, usage_date=yesterday, tokens_used=999_999))
    session.flush()

    assert tokens_used_today(session, user.id) == 0


def test_recording_zero_tokens_creates_no_row(session):
    from src.models.user import User

    user = User(email="budget-zero@example.com", password_hash="x")
    session.add(user)
    session.flush()

    record_tokens(session, user.id, 0)

    assert tokens_used_today(session, user.id) == 0
