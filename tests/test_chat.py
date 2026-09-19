import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest.mock import ANY, patch

from sqlalchemy import func, select

from src.api import deps
from src.models.chat import Message, MessagePlan
from src.services.generation import Answer
from src.services.plan_search import PlanResult
from src.services.profile import PlanProfile, age_on, today
from src.services.retrieval import RetrievedChunk
from tests.helpers import PROFILE


def _auth_headers(client, email="bob@example.com", password="correct-horse-1"):
    token = client.post("/api/auth/register", json={"email": email, "password": password, **PROFILE}).get_json()["access_token"]
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
    mock_answer_query.return_value = Answer("A deductible is the amount you pay before coverage kicks in.", _fake_chunks())
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
    mock_answer_query.assert_called_once_with("What is a deductible?", [], profile=ANY, shown_plans=())
    # The saved profile reaches the plan tool from the server, not the prompt (ADR 0012).
    assert mock_answer_query.call_args.kwargs["profile"] == PlanProfile(
        zip_code="00001", age=age_on(date(1990, 5, 17), today()), county_fips="99001"
    )


@patch("src.api.routes.chat.answer_query")
def test_citations_survive_reopening_the_thread(mock_answer_query, client):
    """The reason this table exists: a restored transcript has to keep its
    grounding, or an answer reads as an ungrounded assertion (ADR 0007)."""
    mock_answer_query.return_value = Answer("A deductible is what you pay first.", _fake_chunks())
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
    mock_answer_query.return_value = Answer("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hello"}, headers=headers)

    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()

    assert next(m for m in reopened if m["role"] == "user")["sources"] == []


@patch("src.api.routes.chat.answer_query")
def test_deleting_a_thread_takes_its_citations(mock_answer_query, client):
    mock_answer_query.return_value = Answer("answer", _fake_chunks())
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "hello"}, headers=headers)

    assert client.delete(f"/api/chat/threads/{thread_id}", headers=headers).status_code == 204
    assert client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).status_code == 404


@patch("src.api.routes.chat.answer_query")
def test_an_answer_with_no_retrieved_context_stores_no_citations(mock_answer_query, client):
    mock_answer_query.return_value = Answer("I couldn't find an answer to that.", [])
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    body = client.post(
        f"/api/chat/threads/{thread_id}/messages", json={"content": "unanswerable"}, headers=headers
    ).get_json()

    assert body["sources"] == []


@patch("src.api.routes.chat.answer_query")
def test_follow_up_receives_the_earlier_turns(mock_answer_query, client):
    mock_answer_query.return_value = Answer("answer", _fake_chunks())
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
    mock_answer_query.return_value = Answer("answer", _fake_chunks())
    headers = _auth_headers(client)
    first = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    second = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    client.post(f"/api/chat/threads/{first}/messages", json={"content": "in thread one"}, headers=headers)
    client.post(f"/api/chat/threads/{second}/messages", json={"content": "in thread two"}, headers=headers)

    assert mock_answer_query.call_args[0][1] == []


@patch("src.api.routes.chat.answer_query")
def test_first_message_titles_the_thread(mock_answer_query, client):
    mock_answer_query.return_value = Answer("answer", _fake_chunks())
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


# Plan cards (ADR 0011)

def _plan(plan_id, premium, *, drug=None):
    """A plan as search_plans returns it; `premium=None` means CMS gave no live price."""
    return PlanResult(
        hios_plan_id=plan_id, plan_year=2026, name=f"Plan {plan_id}", issuer="CHRISTUS Health Plan",
        metal_level="Silver", plan_type="HMO",
        monthly_premium=None if premium is None else Decimal(premium),
        premium_reference=Decimal("535.35"), deductible=Decimal("5990.00"), drug_deductible=drug,
        out_of_pocket_max=Decimal("9200.00"), hsa_eligible=False, quality_rating=3,
        benefits_url="https://example.com/sbc.pdf", county_name="Anderson", state="TX",
        premium_age=None if premium is None else 34,
    )


def _ask(client, answer):
    headers = _auth_headers(client)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    with patch("src.api.routes.chat.answer_query", return_value=answer):
        sent = client.post(f"/api/chat/threads/{thread_id}/messages",
                           json={"content": "Silver plans in 75801? I'm 34."}, headers=headers)
    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    return headers, thread_id, sent, reopened


def test_plans_survive_reopening_the_thread_exactly_as_shown(client):
    """A reloaded thread must match the live one (ADR 0007): same plans, same
    order, same money to the cent, and the age each premium was priced for."""
    # Shown in an order that sorts neither way by ID, so only position can keep it.
    plans = (
        _plan("66252TX0380010", "620.15"),
        _plan("33602TX0460725", "601.05"),
        _plan("40220TX0080031", "620.26", drug=Decimal("5500.00")),
    )
    _, _, sent, reopened = _ask(client, Answer("Here are three plans.", [], plans))

    assert sent.status_code == 201
    live = sent.get_json()["plans"]
    assert [p["hios_plan_id"] for p in live] == ["66252TX0380010", "33602TX0460725", "40220TX0080031"]
    assert live[0] == {
        "hios_plan_id": "66252TX0380010", "plan_year": 2026, "name": "Plan 66252TX0380010",
        "issuer": "CHRISTUS Health Plan", "metal_level": "Silver", "plan_type": "HMO",
        "monthly_premium": "620.15", "premium_age": 34, "premium_reference": "535.35",
        "deductible": "5990.00", "drug_deductible": None, "out_of_pocket_max": "9200.00",
        "hsa_eligible": False, "quality_rating": 3, "county_name": "Anderson", "state": "TX",
        "benefits_url": "https://example.com/sbc.pdf",
    }
    assert live[2]["drug_deductible"] == "5500.00"
    assert next(m for m in reopened if m["role"] == "assistant")["plans"] == live


def test_an_unpriced_plan_stays_unpriced_after_a_reload(client):
    """Stored as $0 or given an age, it would read as a live price after a reload."""
    _, _, _, reopened = _ask(client, Answer("CMS was unavailable.", [], (_plan("66252TX0380010", None),)))

    card = next(m for m in reopened if m["role"] == "assistant")["plans"][0]
    assert (card["monthly_premium"], card["premium_age"], card["premium_reference"]) == (None, None, "535.35")


def test_messages_without_plans_carry_none(client):
    _, _, sent, reopened = _ask(client, Answer("A deductible is what you pay first.", _fake_chunks()))

    assert sent.get_json()["plans"] == []
    assert [m["plans"] for m in reopened] == [[], []]


def test_deleting_a_thread_takes_its_plans(client):
    headers, thread_id, _, _ = _ask(client, Answer("plans", [], (_plan("66252TX0380010", "620.15"),)))
    stored = select(func.count()).select_from(MessagePlan).where(
        MessagePlan.message_id.in_(select(Message.id).where(Message.thread_id == uuid.UUID(thread_id)))
    )
    # The client's requests run on their own connection and transaction; the
    # patched SessionLocal is the one way to read what they wrote.
    db = deps.SessionLocal()
    assert db.scalar(stored) == 1

    assert client.delete(f"/api/chat/threads/{thread_id}", headers=headers).status_code == 204
    assert db.scalar(stored) == 0


def test_a_childs_age_prices_the_search_but_is_never_stored(client):
    """ADR 0012: nothing about someone under 13 is stored. The question text is
    kept as typed, but the saved card drops the age — live and after a reload."""
    child = replace(_plan("66252TX0380010", "301.20"), premium_age=10)
    adult = replace(_plan("66252TX0380008", "620.15"), premium_age=13)
    _, _, sent, reopened = _ask(client, Answer("Plans for your child.", [], (child, adult)))

    live = sent.get_json()["plans"]
    assert [(p["monthly_premium"], p["premium_age"]) for p in live] == [("301.20", None), ("620.15", 13)]
    assert next(m for m in reopened if m["role"] == "assistant")["plans"] == live


# Coverage follow-ups (ADR 0014)

def test_a_follow_up_is_given_the_plans_last_shown_and_its_sbc_citations_are_kept(client):
    first = (_plan("66252TX0380010", "620.15"), _plan("33602TX0460725", "601.05"))
    headers, thread_id, _, _ = _ask(client, Answer("Two plans.", [], first))
    passage = RetrievedChunk("sbc_2026_ab_s01_c00", "If you have a test\nImaging 40%",
                             "Plan 33602TX0460725 - Summary of Benefits - If you have a test.pdf", 0.21)

    def ask(question, answer):
        with patch("src.api.routes.chat.answer_query", return_value=answer) as answer_query:
            sent = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": question}, headers=headers)
        return answer_query.call_args.kwargs["shown_plans"], sent.get_json()

    shown, reply = ask("Does the second one cover MRIs?", Answer("Imaging is 40%.", [passage]))
    # An answer without plans leaves the last table the one referred to.
    shown_again, _ = ask("And the first?", Answer("No plans here.", []))

    assert [(p.position, p.plan_id, p.plan_year) for p in shown] == [(1, "66252TX0380010", 2026), (2, "33602TX0460725", 2026)]
    assert shown_again == shown
    assert reply["sources"] == [{"chunk_id": passage.chunk_id, "source": passage.source, "relevance": 0.21}]
