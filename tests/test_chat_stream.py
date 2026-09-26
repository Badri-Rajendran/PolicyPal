"""POST /api/chat/threads/<id>/messages/stream: an answer as Server-Sent Events (ADR 0027)."""
import json
import uuid
from unittest.mock import patch

import flask
import openai
import pytest

from src.api import deps
from src.models.chat import MessageSource
from src.services.generation import Answer, Delta, Done, Notice, Reset, Stage
from src.services.passages import content_hash
from src.services.retrieval import RetrievedChunk
from tests.test_chat import _auth_headers

CHUNKS = [RetrievedChunk("c1", "A deductible is...", "wiki_Health.txt", 0.9)]


def _events(resp):
    out = []
    for block in resp.get_data(as_text=True).strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _thread(client, email):
    headers = _auth_headers(client, email=email)
    return headers, client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]


def _url(thread_id):
    return f"/api/chat/threads/{thread_id}/messages/stream"


def _stream(client, headers, thread_id, events, content="What is a deductible?"):
    # buffered: the body is read inside the patch, where the stream runs.
    with patch("src.api.routes.chat.answer_query_events", return_value=iter(events)) as source:
        resp = client.post(_url(thread_id), json={"content": content}, headers=headers, buffered=True)
    resp.source = source
    return resp


def _saved(client, headers, thread_id):
    return client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()


def test_the_happy_path_streams_in_order_and_saves_what_done_carries(client):
    headers, thread_id = _thread(client, "stream-ok@example.com")
    answer = Answer("Notice.\n\nA deductible is what you pay first.", CHUNKS)
    resp = _stream(client, headers, thread_id, [
        Stage("searching"), Notice("Notice."), Stage("writing"), Delta("A deductible "), Delta("is what you pay first."),
        Done(answer)])

    assert resp.status_code == 200
    assert resp.mimetype == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache" and resp.headers["X-Accel-Buffering"] == "no"
    events = _events(resp)
    assert [e for e, _ in events] == ["user_message", "stage", "notice", "stage", "delta", "delta", "done"]
    assert [d for _, d in events[1:6]] == [{"stage": "searching"}, {"text": "Notice."}, {"stage": "writing"},
                                           {"text": "A deductible "}, {"text": "is what you pay first."}]
    done = events[-1][1]
    assert done["message"]["content"] == answer.text
    assert done["message"]["sources"][0]["id"]
    assert done["thread"]["id"] == thread_id and done["thread"]["title"] == "What is a deductible?"
    saved = _saved(client, headers, thread_id)
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1] == done["message"]
    assert saved[0] == events[0][1]["message"]


def test_the_question_history_and_profile_reach_generation(client):
    headers, thread_id = _thread(client, "stream-args@example.com")
    _stream(client, headers, thread_id, [Done(Answer("First.", CHUNKS))], content="First?")

    resp = _stream(client, headers, thread_id, [Done(Answer("Second.", CHUNKS))], content="Second?")

    args, kwargs = resp.source.call_args
    assert args == ("Second?", [{"role": "user", "content": "First?"}, {"role": "assistant", "content": "First."}])
    assert kwargs["profile"] is not None and kwargs["shown_plans"] == ()


def test_a_saved_citation_carries_its_passage_hash(client):
    headers, thread_id = _thread(client, "stream-hash@example.com")
    done = _events(_stream(client, headers, thread_id, [Done(Answer("A.", CHUNKS))]))[-1][1]

    row = deps.SessionLocal().get(MessageSource, uuid.UUID(done["message"]["sources"][0]["id"]))
    assert row.content_sha256 == content_hash("A deductible is...")


def test_the_question_is_committed_before_the_model_is_called(client):
    headers, thread_id = _thread(client, "stream-commit@example.com")
    seen = {}

    def source(*_args, **_kwargs):
        db = flask.g.get("db")
        seen["open_transaction"] = db is not None and db.in_transaction()
        seen["questions"] = [m["role"] for m in _saved(client, headers, thread_id)]
        yield Done(Answer("A.", CHUNKS))

    with patch("src.api.routes.chat.answer_query_events", side_effect=source):
        client.post(_url(thread_id), json={"content": "Q?"}, headers=headers, buffered=True)

    assert seen == {"open_transaction": False, "questions": ["user"]}


def test_reset_is_forwarded(client):
    headers, thread_id = _thread(client, "stream-reset@example.com")
    events = _events(_stream(client, headers, thread_id, [Delta("x"), Reset(), Done(Answer("y", CHUNKS))]))
    assert [e for e, _ in events] == ["user_message", "delta", "reset", "done"]
    assert events[2][1] == {}


def test_errors_before_the_stream_are_not_streamed(client):
    headers, thread_id = _thread(client, "stream-pre@example.com")
    with patch("src.api.routes.chat.answer_query_events") as source:
        missing = client.post(_url("00000000-0000-0000-0000-000000000000"), json={"content": "x"}, headers=headers)
        malformed = client.post(_url("nope"), json={"content": "x"}, headers=headers)
        invalid = client.post(_url(thread_id), json={"content": ""}, headers=headers)
        too_long = client.post(_url(thread_id), json={"content": "x" * 4001}, headers=headers)
    assert (missing.status_code, malformed.status_code) == (404, 404)
    assert (invalid.status_code, invalid.mimetype) == (422, "application/json")
    assert too_long.status_code == 422
    source.assert_not_called()
    assert _saved(client, headers, thread_id) == []


def test_another_users_thread_is_404(client):
    _, thread_id = _thread(client, "stream-owner@example.com")
    other = _auth_headers(client, email="stream-other@example.com")
    with patch("src.api.routes.chat.answer_query_events") as source:
        resp = client.post(_url(thread_id), json={"content": "x"}, headers=other)
    assert resp.status_code == 404
    source.assert_not_called()


def test_streaming_requires_auth(client):
    resp = client.post(_url("00000000-0000-0000-0000-000000000000"), json={"content": "x"})
    assert (resp.status_code, resp.mimetype) == (401, "application/json")


def test_an_exhausted_budget_is_a_json_429(client):
    headers, thread_id = _thread(client, "stream-budget@example.com")
    with patch("src.api.routes.chat.budget_exhausted", return_value=True), \
         patch("src.api.routes.chat.answer_query_events") as source:
        resp = client.post(_url(thread_id), json={"content": "x"}, headers=headers)
    assert resp.status_code == 429 and resp.get_json()["error"] == "daily token budget exhausted"
    assert "Retry-After" in resp.headers
    source.assert_not_called()
    assert _saved(client, headers, thread_id) == []


def _failing():
    yield Stage("searching")
    raise openai.APIConnectionError(request=None)


def test_a_model_failure_ends_with_error_and_keeps_the_question(client):
    headers, thread_id = _thread(client, "stream-fail@example.com")
    with patch("src.api.routes.chat.answer_query_events", return_value=_failing()), \
         patch("src.api.routes.chat.token_usage", return_value=11), \
         patch("src.api.routes.chat.record_tokens") as record:
        resp = client.post(_url(thread_id), json={"content": "x"}, headers=headers, buffered=True)
        events = _events(resp)
    assert [e for e, _ in events] == ["user_message", "stage", "error"]
    assert events[-1] == ("error", {"error": "generation failed"})
    record.assert_called_once()
    assert record.call_args.args[2] == 11
    assert [m["role"] for m in _saved(client, headers, thread_id)] == ["user"]


def test_an_unexpected_failure_also_ends_with_error(client):
    headers, thread_id = _thread(client, "stream-bug@example.com")

    def broken():
        yield Stage("searching")
        raise ValueError("a bug")

    with patch("src.api.routes.chat.answer_query_events", return_value=broken()), \
         patch("src.api.routes.chat.record_tokens") as record:
        events = _events(client.post(_url(thread_id), json={"content": "x"}, headers=headers, buffered=True))
    assert events[-1] == ("error", {"error": "generation failed"})
    record.assert_called_once()
    assert [m["role"] for m in _saved(client, headers, thread_id)] == ["user"]


def test_a_real_spend_is_recorded_once_on_success(client):
    headers, thread_id = _thread(client, "stream-spend@example.com")
    with patch("src.api.routes.chat.answer_query_events", return_value=iter([Done(Answer("A.", CHUNKS))])), \
         patch("src.api.routes.chat.token_usage", return_value=21), \
         patch("src.api.routes.chat.record_tokens") as record:
        client.post(_url(thread_id), json={"content": "x"}, headers=headers, buffered=True)
    record.assert_called_once()
    assert record.call_args.args[2] == 21


class _Source:
    """answer_query_events, stopped part-way: records whether it was closed."""

    def __init__(self):
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return Stage("searching")

    def close(self):
        self.closed = True


def test_disconnect_records_spend_once_and_saves_no_answer(client):
    headers, thread_id = _thread(client, "stream-drop@example.com")
    source = _Source()

    with patch("src.api.routes.chat.answer_query_events", return_value=source), \
         patch("src.api.routes.chat.token_usage", return_value=9), \
         patch("src.api.routes.chat.record_tokens") as record:
        resp = client.post(_url(thread_id), json={"content": "x"}, headers=headers, buffered=False)
        stream = iter(resp.response)
        next(stream)              # user_message
        next(stream)              # stage
        resp.close()              # the client goes away
    record.assert_called_once()
    assert record.call_args.args[2] == 9
    assert source.closed          # so the model's stream closes too
    assert [m["role"] for m in _saved(client, headers, thread_id)] == ["user"]


@pytest.mark.parametrize("title", [None, "Kept"])
def test_the_first_answer_titles_an_untitled_thread_only(client, title):
    headers = _auth_headers(client, email=f"stream-title-{title}@example.com")
    thread_id = client.post("/api/chat/threads", json={"title": title}, headers=headers).get_json()["id"]
    done = _events(_stream(client, headers, thread_id, [Done(Answer("A.", CHUNKS))], content="Q about deductibles"))[-1]
    assert done[1]["thread"]["title"] == (title or "Q about deductibles")
