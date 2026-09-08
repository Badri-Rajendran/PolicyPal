"""Every endpoint is rate-limited (CLAUDE.md: throttling behaviour, 429 with
retry headers, on every endpoint). One test per endpoint, all sharing the
same "hammer past the configured limit" shape.
"""
from unittest.mock import patch


def _auth_headers(client, email):
    token = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-1"}).get_json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _hammer(client, method, path, times, headers=None, body=None):
    return [client.open(method=method, path=path, json=body, headers=headers) for _ in range(times)]


def test_register_is_rate_limited(client):
    responses = [
        client.post("/api/auth/register", json={"email": f"reg-rl{i}@example.com", "password": "correct-horse-1"})
        for i in range(6)
    ]

    assert [r.status_code for r in responses[:5]] == [201] * 5
    assert responses[5].status_code == 429
    assert "Retry-After" in responses[5].headers


def test_login_is_rate_limited(client):
    client.post("/api/auth/register", json={"email": "login-rl@example.com", "password": "correct-horse-1"})
    body = {"email": "login-rl@example.com", "password": "correct-horse-1"}

    responses = _hammer(client, "POST", "/api/auth/login", times=11, body=body)

    assert [r.status_code for r in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429
    assert "Retry-After" in responses[10].headers


def test_me_is_rate_limited(client):
    headers = _auth_headers(client, "me-rl@example.com")

    responses = _hammer(client, "GET", "/api/auth/me", times=61, headers=headers)

    assert responses[60].status_code == 429
    assert "Retry-After" in responses[60].headers


def test_list_threads_is_rate_limited(client):
    headers = _auth_headers(client, "list-threads-rl@example.com")

    responses = _hammer(client, "GET", "/api/chat/threads", times=61, headers=headers)

    assert responses[60].status_code == 429


def test_create_thread_is_rate_limited(client):
    headers = _auth_headers(client, "create-thread-rl@example.com")

    responses = _hammer(client, "POST", "/api/chat/threads", times=31, headers=headers, body={})

    assert [r.status_code for r in responses[:30]] == [201] * 30
    assert responses[30].status_code == 429
    assert "Retry-After" in responses[30].headers


def test_delete_thread_is_rate_limited(client):
    headers = _auth_headers(client, "delete-thread-rl@example.com")
    # flask-limiter counts every request that reaches the route, including
    # ones the route logic itself then 404s — a non-existent id is enough.
    fake_id = "00000000-0000-0000-0000-000000000000"

    responses = _hammer(client, "DELETE", f"/api/chat/threads/{fake_id}", times=31, headers=headers)

    assert [r.status_code for r in responses[:30]] == [404] * 30
    assert responses[30].status_code == 429


def test_list_messages_is_rate_limited(client):
    headers = _auth_headers(client, "list-messages-rl@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    responses = _hammer(client, "GET", f"/api/chat/threads/{thread_id}/messages", times=61, headers=headers)

    assert responses[60].status_code == 429


@patch("src.api.routes.chat.answer_query")
def test_send_message_is_rate_limited(mock_answer_query, client):
    mock_answer_query.return_value = ("answer", [])
    headers = _auth_headers(client, "send-message-rl@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    responses = _hammer(
        client, "POST", f"/api/chat/threads/{thread_id}/messages", times=16, headers=headers, body={"content": "hi"}
    )

    assert [r.status_code for r in responses[:15]] == [201] * 15
    assert responses[15].status_code == 429
    assert "Retry-After" in responses[15].headers
