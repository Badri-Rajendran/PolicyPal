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
    assert body["message"]["role"] == "assistant"
    assert "deductible" in body["message"]["content"]
    assert body["sources"][0]["source"] == "wiki_Health.txt"
    mock_answer_query.assert_called_once_with("What is a deductible?")


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


def test_delete_thread(client):
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    delete_resp = client.delete(f"/api/chat/threads/{thread_id}", headers=headers)
    assert delete_resp.status_code == 204

    list_resp = client.get("/api/chat/threads", headers=headers)
    assert list_resp.get_json() == []
