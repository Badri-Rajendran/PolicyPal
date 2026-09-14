from unittest.mock import patch

from src.services.retrieval import RetrievedChunk


def _auth_headers(client, email="bob@example.com", password="correct-horse-1"):
    token = client.post("/api/auth/register", json={"email": email, "password": password}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _fake_chunks():
    return [RetrievedChunk(chunk_id="c1", content="A deductible is...", source="wiki_Health.txt", score=0.9)]


def test_create_and_list_threads(client):
    headers = _auth_headers(client)

    create_resp = client.post("/api/chat/threads", json={}, headers=headers)
    assert create_resp.status_code == 201
    thread_id = create_resp.get_json()["id"]

    list_resp = client.get("/api/chat/threads", headers=headers)
    assert list_resp.status_code == 200
    assert [t["id"] for t in list_resp.get_json()] == [thread_id]


def test_threads_require_auth(client):
    resp = client.get("/api/chat/threads")
    assert resp.status_code == 401


def test_cannot_access_another_users_thread(client):
    owner_headers = _auth_headers(client, email="owner@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=owner_headers).get_json()["id"]

    other_headers = _auth_headers(client, email="other@example.com")
    resp = client.get(f"/api/chat/threads/{thread_id}/messages", headers=other_headers)

    assert resp.status_code == 404


def test_unknown_thread_id_is_404(client):
    headers = _auth_headers(client)
    resp = client.get("/api/chat/threads/00000000-0000-0000-0000-000000000000/messages", headers=headers)

    assert resp.status_code == 404


def test_create_thread_requires_auth(client):
    resp = client.post("/api/chat/threads", json={})
    assert resp.status_code == 401


def test_cannot_post_message_to_another_users_thread(client):
    owner_headers = _auth_headers(client, email="owner2@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=owner_headers).get_json()["id"]

    other_headers = _auth_headers(client, email="other2@example.com")
    resp = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hi"}, headers=other_headers)

    assert resp.status_code == 404


def test_cannot_delete_another_users_thread(client):
    owner_headers = _auth_headers(client, email="owner3@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=owner_headers).get_json()["id"]

    other_headers = _auth_headers(client, email="other3@example.com")
    resp = client.delete(f"/api/chat/threads/{thread_id}", headers=other_headers)

    assert resp.status_code == 404


@patch("src.api.routes.chat.answer_query")
def test_send_message_returns_grounded_answer_with_sources(mock_answer_query, client):
    mock_answer_query.return_value = ("A deductible is the amount you pay before coverage kicks in.", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    resp = client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": "What is a deductible?"}, headers=headers
    )

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["role"] == "assistant"
    assert "deductible" in body["content"]
    assert body["sources"][0]["source"] == "wiki_Health.txt"
    mock_answer_query.assert_called_once_with("What is a deductible?", [])


@patch("src.api.routes.chat.answer_query")
def test_citations_survive_reopening_the_thread(mock_answer_query, client):
    """The reason this table exists: a restored transcript has to keep its
    grounding, or an answer reads as an ungrounded assertion (ADR 0007)."""
    mock_answer_query.return_value = ("A deductible is what you pay first.", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": "What is a deductible?"}, headers=headers
    )

    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assistant = next(m for m in reopened if m["role"] == "assistant")

    assert assistant["sources"][0]["source"] == "wiki_Health.txt"
    assert assistant["sources"][0]["chunk_id"]
    assert 0 < assistant["sources"][0]["relevance"] <= 1


@patch("src.api.routes.chat.answer_query")
def test_a_user_question_carries_no_citations(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hello"}, headers=headers)

    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()

    assert next(m for m in reopened if m["role"] == "user")["sources"] == []


@patch("src.api.routes.chat.answer_query")
def test_deleting_a_thread_takes_its_citations(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hello"}, headers=headers)

    assert client.delete(f"/api/chat/threads/{thread_id}", headers=headers).status_code == 204
    assert client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).status_code == 404


@patch("src.api.routes.chat.answer_query")
def test_an_answer_with_no_retrieved_context_stores_no_citations(mock_answer_query, client):
    mock_answer_query.return_value = ("I couldn't find an answer to that.", [])
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    body = client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": "unanswerable"}, headers=headers
    ).get_json()

    assert body["sources"] == []


@patch("src.api.routes.chat.answer_query")
def test_follow_up_receives_the_earlier_turns(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    url = f"/api/chat/threads/{thread_id}/messages"

    client.post(url, json={"content": "What is a deductible?"}, headers=headers)
    client.post(url, json={"content": "What about for auto?"}, headers=headers)

    question, history = mock_answer_query.call_args[0]

    assert question == "What about for auto?"
    # The earlier exchange, and not the question that is being asked right now.
    assert [turn["role"] for turn in history] == ["user", "assistant"]
    assert history[0]["content"] == "What is a deductible?"
    assert "What about for auto?" not in [turn["content"] for turn in history]


@patch("src.api.routes.chat.answer_query")
def test_history_is_scoped_to_its_own_thread(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", _fake_chunks())
    headers = _auth_headers(client)
    first = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    second = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(f"/api/chat/threads/{first}/messages", json={"content": "in thread one"}, headers=headers)
    client.post(f"/api/chat/threads/{second}/messages", json={"content": "in thread two"}, headers=headers)

    assert mock_answer_query.call_args[0][1] == []


@patch("src.api.routes.chat.answer_query")
def test_first_message_titles_the_thread(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hello there"}, headers=headers)

    thread = client.get("/api/chat/threads", headers=headers).get_json()[0]
    assert thread["title"] == "hello there"


def test_message_validation_error(client):
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    resp = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": ""}, headers=headers)

    assert resp.status_code == 422


def test_message_content_over_max_length_rejected(client):
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    resp = client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": "x" * 4001}, headers=headers
    )

    assert resp.status_code == 422


def test_thread_title_over_max_length_rejected(client):
    headers = _auth_headers(client)
    resp = client.post("/api/chat/threads", json={"title": "x" * 201}, headers=headers)

    assert resp.status_code == 422


def test_delete_thread(client):
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    delete_resp = client.delete(f"/api/chat/threads/{thread_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = client.get("/api/chat/threads", headers=headers)
    assert list_resp.get_json() == []
