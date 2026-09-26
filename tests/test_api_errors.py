"""HTTP errors are JSON, like every other answer the API gives (ADR 0027)."""
from tests.helpers import PROFILE


def _auth_headers(client, email):
    token = client.post("/api/auth/register", json={"email": email, "password": "correct-horse-1", **PROFILE}).get_json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def test_an_unknown_path_is_a_json_404(client):
    resp = client.get("/api/no-such-thing")

    assert (resp.status_code, resp.mimetype) == (404, "application/json")
    assert resp.get_json() == {"error": "not found"}


def test_a_missing_thread_is_a_json_404(client):
    headers = _auth_headers(client, "errors-404@example.com")

    resp = client.get("/api/chat/threads/00000000-0000-0000-0000-000000000000/messages", headers=headers)

    assert (resp.status_code, resp.get_json()) == (404, {"error": "not found"})


def test_a_wrong_method_is_a_json_405_that_keeps_its_allow_header(client):
    resp = client.put("/api/chat/threads")

    assert (resp.status_code, resp.get_json()) == (405, {"error": "method not allowed"})
    assert "GET" in resp.headers["Allow"]


def test_a_rate_limited_request_is_json_and_keeps_retry_after(client):
    body = {"email": "errors-rl@example.com", "password": "wrong-password"}
    responses = [client.post("/api/auth/login", json=body) for _ in range(11)]

    assert responses[10].status_code == 429
    assert responses[10].get_json() == {"error": "too many requests"}
    assert "Retry-After" in responses[10].headers
