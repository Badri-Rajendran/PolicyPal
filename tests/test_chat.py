import hashlib
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import ANY, patch

import pytest
from sqlalchemy import func, select, update

from src.api import deps
from src.models.chat import Message, MessagePlan, MessageSource, Thread
from src.models.chunk import Chunk
from src.models.sbc import SbcChunk, SbcDocument
from src.policypal.config import settings
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

def _plan(plan_id, premium, *, drug=None, sbc_status="ok"):
    """A plan as search_plans returns it; `premium=None` means CMS gave no live price."""
    return PlanResult(
        hios_plan_id=plan_id, plan_year=2026, name=f"Plan {plan_id}", issuer="CHRISTUS Health Plan",
        metal_level="Silver", plan_type="HMO",
        monthly_premium=None if premium is None else Decimal(premium),
        premium_reference=Decimal("535.35"), deductible=Decimal("5990.00"), drug_deductible=drug,
        out_of_pocket_max=Decimal("9200.00"), hsa_eligible=False, quality_rating=3,
        benefits_url="https://example.com/sbc.pdf", county_name="Anderson", state="TX",
        premium_age=None if premium is None else 34, sbc_status=sbc_status,
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
        "benefits_url": "https://example.com/sbc.pdf", "sbc_status": "ok",
    }
    assert live[2]["drug_deductible"] == "5500.00"
    assert next(m for m in reopened if m["role"] == "assistant")["plans"] == live


def test_an_unpriced_plan_stays_unpriced_after_a_reload(client):
    """Stored as $0 or given an age, it would read as a live price after a reload."""
    _, _, _, reopened = _ask(client, Answer("CMS was unavailable.", [], (_plan("66252TX0380010", None),)))

    card = next(m for m in reopened if m["role"] == "assistant")["plans"][0]
    assert (card["monthly_premium"], card["premium_age"], card["premium_reference"]) == (None, None, "535.35")


def test_a_card_keeps_whether_its_sbc_could_be_read_when_shown(client):
    """ADR 0017: a plan with no readable document says so, live and after a reload.
    A card saved before this was recorded reads as null, not as readable."""
    plans = (_plan("66252TX0380010", "620.15", sbc_status="blocked"), _plan("33602TX0460725", "601.05"),
             _plan("40220TX0080031", "620.26", sbc_status=None))
    _, _, sent, reopened = _ask(client, Answer("Three plans.", [], plans))

    live = sent.get_json()["plans"]
    assert [p["sbc_status"] for p in live] == ["blocked", "ok", None]
    assert next(m for m in reopened if m["role"] == "assistant")["plans"] == live


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
    assert reply["sources"] == [{"id": ANY, "chunk_id": passage.chunk_id, "source": passage.source, "relevance": 0.21}]


def _new_thread(client, headers):
    return client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]


def test_rename_thread_sets_a_stripped_title(client):
    headers = _auth_headers(client, email="rename@example.com")
    thread_id = _new_thread(client, headers)

    resp = client.patch(f"/api/chat/threads/{thread_id}", json={"title": "  Silver plans, San Diego  "}, headers=headers)

    assert resp.status_code == 200
    assert resp.get_json()["title"] == "Silver plans, San Diego"
    listed = client.get("/api/chat/threads", headers=headers).get_json()
    assert listed[0]["title"] == "Silver plans, San Diego"


def test_rename_does_not_move_a_thread_up_the_list(client):
    # Every request in a test shares one transaction, where now() never moves,
    # so a bump could not be seen: the thread is first dated a week back.
    headers = _auth_headers(client, email="rename-order@example.com")
    older = _new_thread(client, headers)
    newer = _new_thread(client, headers)
    week_ago = datetime.now(UTC) - timedelta(days=7)
    db = deps.SessionLocal()
    db.execute(update(Thread).where(Thread.id == uuid.UUID(older)).values(updated_at=week_ago))
    db.flush()

    client.patch(f"/api/chat/threads/{older}", json={"title": "Renamed"}, headers=headers)

    after = client.get("/api/chat/threads", headers=headers).get_json()
    assert [t["id"] for t in after] == [newer, older]
    assert datetime.fromisoformat(after[1]["updated_at"]) == week_ago


@pytest.mark.parametrize("title", ["", "   ", "x" * 201, " " + "x" * 201 + " ", 123, None])
def test_rename_rejects_a_blank_long_or_non_text_title(client, title):
    headers = _auth_headers(client, email=f"rename-bad-{uuid.uuid4().hex[:8]}@example.com")
    thread_id = _new_thread(client, headers)

    resp = client.patch(f"/api/chat/threads/{thread_id}", json={"title": title}, headers=headers)

    assert resp.status_code == 422


@pytest.mark.parametrize("title", ["x" * 200, "   " + "x" * 200 + "   "])
def test_rename_accepts_200_characters_counted_after_trimming(client, title):
    headers = _auth_headers(client, email=f"rename-200-{len(title)}@example.com")
    thread_id = _new_thread(client, headers)

    resp = client.patch(f"/api/chat/threads/{thread_id}", json={"title": title}, headers=headers)

    assert resp.status_code == 200
    assert resp.get_json()["title"] == "x" * 200


@pytest.mark.parametrize("thread_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"])
def test_rename_of_a_missing_thread_is_404(client, thread_id):
    headers = _auth_headers(client, email="rename-missing@example.com")
    assert client.patch(f"/api/chat/threads/{thread_id}", json={"title": "x"}, headers=headers).status_code == 404


def test_cannot_rename_another_users_thread(client):
    owner = _auth_headers(client, email="rename-owner@example.com")
    thread_id = _new_thread(client, owner)
    other = _auth_headers(client, email="rename-other@example.com")

    assert client.patch(f"/api/chat/threads/{thread_id}", json={"title": "x"}, headers=other).status_code == 404
    listed = client.get("/api/chat/threads", headers=owner).get_json()
    assert listed[0]["title"] is None


def test_rename_requires_auth(client):
    assert client.patch("/api/chat/threads/00000000-0000-0000-0000-000000000000", json={"title": "x"}).status_code == 401


@patch("src.api.routes.chat.answer_query")
def test_sources_carry_an_id_and_the_passage_hash(mock_answer_query, client):
    mock_answer_query.return_value = Answer("A deductible is what you pay first.", _fake_chunks())
    headers = _auth_headers(client, email="hash@example.com")
    thread_id = _new_thread(client, headers)

    sent = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "Deductible?"}, headers=headers)

    source = sent.get_json()["sources"][0]
    assert uuid.UUID(source["id"])
    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assert next(m for m in reopened if m["role"] == "assistant")["sources"][0]["id"] == source["id"]
    row = deps.SessionLocal().get(MessageSource, uuid.UUID(source["id"]))
    assert row.content_sha256 == hashlib.sha256(b"A deductible is...").hexdigest()


_WIKI = RetrievedChunk(chunk_id="wikipedia_Test_source_s0_c00", content="Health insurance covers medical expenses.",
                       source="wiki_Health_insurance.txt", score=0.88)


def _one_source(client, email, chunks=None, answer_text="Health insurance covers costs."):
    headers = _auth_headers(client, email=email)
    thread_id = _new_thread(client, headers)
    with patch("src.api.routes.chat.answer_query", return_value=Answer(answer_text, chunks or [_WIKI])):
        sent = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "What is it?"}, headers=headers)
    return headers, sent.get_json()["sources"][0]["id"]


def _store_chunk(chunk_id, source, content):
    db = deps.SessionLocal()
    db.add(Chunk(chunk_id=chunk_id, source=source, content=content, embedding=[0.0] * settings.embedding_dim))
    db.flush()


def test_a_source_reads_as_missing_when_its_chunk_is_gone(client):
    headers, source_id = _one_source(client, "src-missing@example.com")

    resp = client.get(f"/api/chat/sources/{source_id}", headers=headers)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == source_id
    assert (body["kind"], body["title"], body["status"], body["quote"]) == ("wikipedia", "Health insurance", "missing", None)
    assert body["url"] == "https://en.wikipedia.org/wiki/Health_insurance"
    assert body["license"] == {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}


def test_a_source_quotes_its_chunk(client):
    _store_chunk(_WIKI.chunk_id, _WIKI.source, _WIKI.content)
    headers, source_id = _one_source(client, "src-ok@example.com")

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert (body["status"], body["quote"], body["document"], body["section"]) == (
        "ok", "Health insurance covers medical expenses.", "Wikipedia article", None)


def test_a_source_whose_chunk_was_rebuilt_is_changed_and_unquoted(client):
    _store_chunk(_WIKI.chunk_id, _WIKI.source, "Something else entirely now.")
    headers, source_id = _one_source(client, "src-changed@example.com")

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert (body["status"], body["quote"]) == ("changed", None)


def test_an_older_citation_without_a_hash_is_unverified(client):
    _store_chunk(_WIKI.chunk_id, _WIKI.source, _WIKI.content)
    headers, source_id = _one_source(client, "src-old@example.com")
    db = deps.SessionLocal()
    db.execute(update(MessageSource).where(MessageSource.id == uuid.UUID(source_id)).values(content_sha256=None))
    db.flush()

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert (body["status"], body["quote"]) == ("unverified", _WIKI.content)


def test_a_healthcare_gov_source(client):
    chunk = RetrievedChunk("healthcare_gov_glossary_Test_source_s0_c00", "Copayment: A fixed amount you pay.",
                           "hcg_glossary_Copayment.md", 0.7)
    _store_chunk(chunk.chunk_id, chunk.source, chunk.content)
    headers, source_id = _one_source(client, "src-hcg@example.com", [chunk])

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert (body["kind"], body["title"], body["document"], body["status"], body["url"], body["license"]) == (
        "healthcare_gov", "Copayment", "HealthCare.gov glossary", "ok", None, None)


def _sbc_source(client, email, url):
    content = "Urgent care | $50 copay/visit; deductible does not apply"
    db = deps.SessionLocal()
    doc = SbcDocument(url=url, plan_year=2026, status="ok")
    db.add(doc)
    db.flush()
    db.add(SbcChunk(document_id=doc.id, chunk_id="sbc_2026_testsrc_s11_c00",
                    section="If you need immediate medical attention", position=0, content=content))
    db.flush()
    chunk = RetrievedChunk("sbc_2026_testsrc_s11_c00", content,
                           "Sharp Silver 70 Premier HMO - Summary of Benefits - If you need immediate medical attention.pdf",
                           0.5)
    return _one_source(client, email, [chunk], answer_text="Urgent care is a $50 copay.")


def test_an_sbc_source(client):
    headers, source_id = _sbc_source(client, "src-sbc@example.com", "https://www.sharphealthplan.com/sbc.pdf")

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert body == {
        "id": source_id, "kind": "sbc", "title": "Sharp Silver 70 Premier HMO",
        "document": "Summary of Benefits and Coverage, 2026", "section": "If you need immediate medical attention",
        "quote": "Urgent care | $50 copay/visit; deductible does not apply", "status": "ok",
        "url": "https://www.sharphealthplan.com/sbc.pdf", "license": None,
    }


@pytest.mark.parametrize("url", ["http://www.sharphealthplan.com/sbc.pdf", "https://localhost/sbc.pdf"])
def test_an_unsafe_sbc_link_is_not_returned(client, url):
    headers, source_id = _sbc_source(client, f"src-unsafe-{len(url)}@example.com", url)

    assert client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()["url"] is None


def test_another_users_source_is_404(client):
    _, source_id = _one_source(client, "src-owner@example.com")
    other = _auth_headers(client, email="src-other@example.com")
    assert client.get(f"/api/chat/sources/{source_id}", headers=other).status_code == 404


@pytest.mark.parametrize("source_id", ["00000000-0000-0000-0000-000000000000", "nope"])
def test_a_missing_source_is_404(client, source_id):
    headers = _auth_headers(client, email="src-none@example.com")
    assert client.get(f"/api/chat/sources/{source_id}", headers=headers).status_code == 404


def test_sources_require_auth(client):
    assert client.get("/api/chat/sources/00000000-0000-0000-0000-000000000000").status_code == 401
