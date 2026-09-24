from flask_jwt_extended import create_access_token
from sqlalchemy import delete

from src.api import deps
from src.models.user import User
from tests.helpers import PROFILE


def _register(client, email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/register", json={"email": email, "password": password, **PROFILE})


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


def test_login_validation_error(client):
    resp = client.post("/api/auth/login", json={"email": "not-an-email"})

    assert resp.status_code == 422


def test_a_token_naming_a_deleted_account_is_rejected_not_a_server_error(client, app):
    """Every view dereferences get_current_user(), so returning None was a 500."""
    token = _register(client).get_json()["access_token"]
    db = deps.SessionLocal()
    db.execute(delete(User).where(User.email == "alice@example.com"))
    db.commit()
    db.close()

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "invalid session"}


def test_a_token_whose_subject_is_not_a_user_id_is_rejected(client, app):
    with app.app_context():
        token = create_access_token(identity="not-a-uuid")

    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 401
    assert resp.get_json() == {"error": "invalid session"}
