"""Signup's profile, the profile endpoints and the county lookup (ADR 0012).

The rule that matters most: nobody under 13 gets an account, and a refused
signup stores nothing about them. ZIP codes come from `tests.helpers`:
00001 is one county, 00002 two, 00009 is in Illinois.
"""
from datetime import date, timedelta

from sqlalchemy import func, select

from src.api import deps
from src.models.user import User
from src.services.profile import today
from tests.helpers import PROFILE


def _years_ago(years: int) -> date:
    on = today()
    try:
        return on.replace(year=on.year - years)
    except ValueError:  # 29 February, in a year without one
        return on.replace(year=on.year - years, day=28)


def _register(client, email="alice@example.com", **profile):
    body = {"email": email, "password": "correct-horse-1", **PROFILE, **profile}
    return client.post("/api/auth/register", json=body)


def _headers(client, email="alice@example.com", **profile):
    return {"Authorization": f"Bearer {_register(client, email, **profile).get_json()['access_token']}"}


def _accounts(email) -> int:
    # The client's requests run on their own connection; this reads through it.
    return deps.SessionLocal().scalar(select(func.count()).select_from(User).where(User.email == email))


def _field_errors(response) -> dict:
    return {d["field"]: d["message"] for d in response.get_json()["details"]}


def test_one_day_short_of_13_is_refused_and_nothing_is_stored(client):
    dob = (_years_ago(13) + timedelta(days=1)).isoformat()
    resp = _register(client, "twelve@example.com", date_of_birth=dob)

    assert resp.status_code == 422
    assert "at least 13" in _field_errors(resp)["date_of_birth"]
    assert dob not in resp.get_data(as_text=True)
    assert _accounts("twelve@example.com") == 0


def test_a_13th_birthday_today_is_old_enough(client):
    resp = _register(client, "thirteen@example.com", date_of_birth=_years_ago(13).isoformat())

    assert resp.status_code == 201
    assert resp.get_json()["user"]["profile_complete"] is True


def test_the_token_response_carries_no_profile_values(client):
    """It is kept in sessionStorage by the browser; the profile is fetched on demand instead."""
    user = _register(client).get_json()["user"]

    assert set(user) == {"id", "email", "created_at", "profile_complete"}


def test_dates_that_cannot_be_a_birth_date_are_refused(client):
    tomorrow = (today() + timedelta(days=1)).isoformat()

    assert "future" in _field_errors(_register(client, "a@example.com", date_of_birth=tomorrow))["date_of_birth"]
    assert _register(client, "b@example.com", date_of_birth="2010-02-30").status_code == 422
    assert _register(client, "c@example.com", date_of_birth=_years_ago(121).isoformat()).status_code == 422


def test_a_zip_code_must_be_real_and_its_county_chosen_when_there_are_several(client):
    unknown = _register(client, "a@example.com", zip_code="00404")
    unchosen = _register(client, "b@example.com", zip_code="00002")
    foreign = _register(client, "c@example.com", zip_code="00002", county_fips="99003")
    chosen = _register(client, "d@example.com", zip_code="00002", county_fips="99002")

    assert "zip_code" in _field_errors(unknown)
    assert _field_errors(unchosen) == {"county_fips": "Choose your county."}
    assert _field_errors(foreign) == {"county_fips": "Choose a county in this ZIP code."}
    assert chosen.status_code == 201
    assert _accounts("a@example.com") + _accounts("b@example.com") + _accounts("c@example.com") == 0


def test_a_zip_code_in_a_state_with_its_own_exchange_is_accepted(client):
    headers = _headers(client, zip_code="00009")

    profile = client.get("/api/profile", headers=headers).get_json()

    assert (profile["state"], profile["marketplace_state"]) == ("IL", False)


def test_the_profile_is_read_and_changed_only_by_its_owner(client):
    headers = _headers(client)

    assert client.get("/api/profile").status_code == 401
    assert client.put("/api/profile", json=PROFILE).status_code == 401
    assert client.get("/api/profile", headers=headers).get_json() == {
        "zip_code": "00001", "date_of_birth": "1990-05-17", "county_fips": "99001",
        "county_name": "Alpha", "state": "TX", "marketplace_state": True,
    }

    changed = client.put("/api/profile", headers=headers,
                         json={"zip_code": "00002", "date_of_birth": "1985-01-02", "county_fips": "99002"})
    assert changed.status_code == 200
    assert (changed.get_json()["county_name"], changed.get_json()["date_of_birth"]) == ("Beta", "1985-01-02")


def test_a_profile_cannot_be_changed_to_under_13(client):
    headers = _headers(client)

    resp = client.put("/api/profile", headers=headers,
                      json={**PROFILE, "date_of_birth": _years_ago(10).isoformat()})

    assert resp.status_code == 422
    assert client.get("/api/profile", headers=headers).get_json()["date_of_birth"] == "1990-05-17"


def test_the_county_lookup_serves_the_signup_form(client):
    found = client.get("/api/counties?zip=00002")

    assert found.status_code == 200
    assert found.get_json() == {
        "counties": [
            {"county_fips": "99001", "county_name": "Alpha", "state": "TX"},
            {"county_fips": "99002", "county_name": "Beta", "state": "TX"},
        ],
        "marketplace_state": True,
    }
    assert client.get("/api/counties?zip=00404").status_code == 404
    assert client.get("/api/counties?zip=7580").status_code == 422
    assert client.get("/api/counties").status_code == 422
