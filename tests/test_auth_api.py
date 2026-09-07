def _register(client, email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def test_register_success(client):
    resp = _register(client)

    assert resp.status_code == 201
    body = resp.get_json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["access_token"]
    assert "password" not in body["user"]


def test_register_duplicate_email_rejected(client):
    _register(client)
    resp = _register(client)

    assert resp.status_code == 409


def test_register_validation_error_does_not_leak_password(client):
    resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "short"})

    assert resp.status_code == 422
    body = resp.get_json()
    assert "short" not in str(body)


def test_login_success(client):
    _register(client)
    resp = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "correct-horse-1"})

    assert resp.status_code == 200
    assert resp.get_json()["access_token"]


def test_login_wrong_password_rejected(client):
    _register(client)
    resp = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})

    assert resp.status_code == 401


def test_login_unknown_email_rejected(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever1"})

    assert resp.status_code == 401


def test_me_requires_auth(client):
    resp = client.get("/api/auth/me")

    assert resp.status_code == 401


def test_me_returns_current_user(client):
    token = _register(client).get_json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.get_json()["email"] == "alice@example.com"


def test_register_is_rate_limited(client):
    responses = [_register(client, email=f"user{i}@example.com") for i in range(6)]

    assert [r.status_code for r in responses[:5]] == [201] * 5
    assert responses[5].status_code == 429
    assert "Retry-After" in responses[5].headers
