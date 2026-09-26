# Chat redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved chat redesign.

- **Part A (backend PR):** streaming answers, renaming threads and cited
  passages.
- **Part B (frontend PR):** the new chat, sign-in and profile screens.

**Architecture:**

- **Backend.** Part A adds three endpoints to the existing chat blueprint.
  `generation.answer` becomes a thin wrapper over an event generator
  (`answer_events`), which the new Server-Sent-Events route also consumes. A
  pure `passages` service turns a stored citation into a brief, credited
  quote.
- **Frontend.** Part B restyles the React app on the design's tokens. It
  renders answers as Markdown, with the citation markers turned into
  components, and it streams through a `fetch` reader.
- **Running the parts.** They run in parallel, one agent each. Part B codes
  against the contracts in the spec (section 3) with mocked services.

**Tech Stack:**

- **Backend:** Flask 3.1, SQLAlchemy 2.0, Alembic, Pydantic, flask-limiter 4.1,
  the openai 3.13 SDK and pytest.
- **Frontend:** React 19 (JSX), Vite 8, Vitest and React Testing Library, plus
  the new `lucide-react`, `motion`, `react-markdown` and `remark-gfm`.

**Spec:** `docs/superpowers/specs/2026-09-26-chat-redesign-design.md`. The
mockups are in `docs/design/chat-redesign/` (read `README.md` there first).
Every part of the spec is binding; this plan says how to build it.

## Global Constraints

- **Branches.** Part A goes on `feature_chat_redesign_api`, and Part B on
  `feature_chat_redesign_ui`, branched from the plan commit. Never commit to
  `main`.
- **No attribution.** Commits and PRs carry no Claude or AI co-author lines
  (CLAUDE.md overrides any tool reminder).
- **CHANGELOG.** Update `CHANGELOG.md` (`## Unreleased`) in every commit with
  crisp bullets.
- **Never commit** a `.env`, credentials, or real user data. Nothing under
  `data/` is ever committed or deleted.
- **SQL.** Parameterised SQLAlchemy only. Never log question text, answer text,
  passages, ZIP codes, ages or dates of birth; log ids and lengths.
- **Ownership failures return 404, never 403.**
- **Rate limits:**

  | Endpoint | Limit |
  | --- | --- |
  | Rename | 30 per minute |
  | Source lookup | 60 per minute |
  | Both send routes | 15 per minute, **shared** (`scope="chat_send"`) |
- **Excerpts are ≤300 characters** of passage text, plus `… ` or ` …` marks.
  A URL is returned only when it is `https` and `unsafe_reason(url) is None`.
- **Event names** are exactly `user_message`, `stage`, `notice`, `delta`,
  `reset`, `done` and `error`. **Stage codes** are exactly `understanding`,
  `searching`, `plans`, `coverage` and `writing`.
- **Passage `kind`** is exactly `sbc`, `wikipedia`, `healthcare_gov` or
  `other`. **`status`** is exactly `ok`, `unverified`, `changed` or `missing`.
- **Frontend dependencies:** `lucide-react`, `motion`, `react-markdown` and
  `remark-gfm`, pinned to exact versions (no `^`), checked with `npm audit
  --omit=dev`. No other new dependency.
- **Markup and copy come from the artboards.** Visual markup, class names and
  copy come from `docs/design/chat-redesign/*.dc.html`, and the tokens from
  `docs/design/chat-redesign/tokens.css`. When the plan names an artboard
  element, port its markup and copy exactly; wording differs only where the
  spec says so.
- **UI copy.** Sentence case. No all-caps labels. No `·` joining metadata. No
  `→` appended to buttons.
- **Quality gates:**
  - Backend: `make check` (ruff, pytest with coverage ≥85%, bandit, pip-audit,
    `alembic check`).
  - Frontend: `npm run lint`, `npm test` and `npm run build`, all green.

## Review Focus

1. **A reset mid-answer.** A round streams text, then calls a tool: the UI
   clears the draft, and `done` equals what was saved. Tests are in Task A5
   (`test_reset_when_a_streamed_round_calls_a_tool`) and Task B6 (`reset`
   clears the text).
2. **A client disconnect mid-stream.** Tokens are recorded exactly once, no
   assistant message is saved, and nothing is left uncommitted. Tested in Task
   A6 (`test_disconnect_records_spend_once_and_saves_no_answer`).
3. **Reloading a thread** must not replay the stamp. An old citation without a
   hash says it may have changed. Tested in Task B7 (the stamp runs only for
   `finishedId`) and Task A4 (`unverified`).
4. **A double send** (Enter held, or two clicks). The composer is disabled
   while an answer is live, and the limit is shared across routes. Tested in
   Task B9 (the composer is disabled while live) and Task A6 (the shared
   limit).
5. **A 390 px viewport.** No sideways page scroll; the plan table scrolls in
   its own box. Tested in Task B11's Playwright pass (`scrollWidth ===
   clientWidth`).

---

# Part A — Backend (`feature_chat_redesign_api`)

Run every command from the repo root. The tests use the local Postgres
(`docker compose up -d db` and `make migrate`, as for any `make check`). The
existing fixtures: `client` shares one rolled-back connection per test;
`_auth_headers(client, email)` in `tests/test_chat.py` registers and returns a
Bearer header.

### Task A1: Renaming a thread

**Files:**
- Modify: `src/schemas/chat.py`: add `ThreadRenameRequest`.
- Modify: `src/api/routes/chat.py`: add the `rename_thread` route after `delete_thread`.
- Test: `tests/test_chat.py`, `tests/test_rate_limits.py`

**Interfaces:**
- Produces: `PATCH /api/chat/threads/<id>` with body `{"title": str}`,
  returning 200 and a `ThreadResponse` JSON.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_chat.py`)

```python
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


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_rename_rejects_a_blank_or_long_title(client, title):
    headers = _auth_headers(client, email=f"rename-bad{len(title)}@example.com")
    thread_id = _new_thread(client, headers)

    resp = client.patch(f"/api/chat/threads/{thread_id}", json={"title": title}, headers=headers)

    assert resp.status_code == 422


@pytest.mark.parametrize("thread_id", ["00000000-0000-0000-0000-000000000000", "not-a-uuid"])
def test_rename_of_a_missing_thread_is_404(client, thread_id):
    headers = _auth_headers(client, email="rename-missing@example.com")
    assert client.patch(f"/api/chat/threads/{thread_id}", json={"title": "x"}, headers=headers).status_code == 404


def test_cannot_rename_another_users_thread(client):
    owner = _auth_headers(client, email="rename-owner@example.com")
    thread_id = _new_thread(client, owner)
    other = _auth_headers(client, email="rename-other@example.com")

    assert client.patch(f"/api/chat/threads/{thread_id}", json={"title": "x"}, headers=other).status_code == 404


def test_rename_requires_auth(client):
    assert client.patch("/api/chat/threads/00000000-0000-0000-0000-000000000000", json={"title": "x"}).status_code == 401
```

At the top of `tests/test_chat.py`, add whichever of these imports are missing:
`import pytest`, `from datetime import UTC, datetime, timedelta`,
`from sqlalchemy import update` and `from src.models.chat import Thread`. The
module already imports `from src.api import deps`. Then
append to `tests/test_rate_limits.py`:

```python
def test_rename_thread_is_rate_limited(client):
    headers = _auth_headers(client, "rename-rl@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    responses = _hammer(client, "PATCH", f"/api/chat/threads/{thread_id}", times=31, headers=headers,
                        body={"title": "t"})

    assert [r.status_code for r in responses[:30]] == [200] * 30
    assert responses[30].status_code == 429
    assert "Retry-After" in responses[30].headers
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_chat.py -k rename tests/test_rate_limits.py -k rename -q`
Expected: FAIL. The PATCH answers 405 Method Not Allowed.

- [ ] **Step 3: Implement**

In `src/schemas/chat.py`, add `field_validator` to the existing pydantic import:

```python
class ThreadRenameRequest(BaseModel):
    title: str = Field(max_length=200)

    @field_validator("title")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value
```

`max_length` is checked before the validator strips, so a title padded past
200 is refused. That is intended and simpler than stripping first.

In `src/api/routes/chat.py`, import `update` from sqlalchemy and
`ThreadRenameRequest`, then add:

```python
@bp.patch("/threads/<thread_id>")
@jwt_required()
@limiter.limit("30 per minute")
def rename_thread(thread_id: str):
    body = parse_body(ThreadRenameRequest)
    db, thread = _get_owned_thread(thread_id)

    # updated_at is the thread's last activity and orders the list: renaming
    # is not activity, so it is set to itself, which stops onupdate firing.
    db.execute(
        update(Thread).where(Thread.id == thread.id).values(title=body.title, updated_at=Thread.updated_at)
    )
    db.refresh(thread)
    return jsonify(ThreadResponse.model_validate(thread, from_attributes=True).model_dump(mode="json"))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_chat.py tests/test_rate_limits.py -q`
Expected: all PASS.

- [ ] **Step 5: CHANGELOG and commit**

Add under `## Unreleased` → `### Added`:
`- \`PATCH /api/chat/threads/<id>\` renames a thread (1–200 characters, trimmed; 30 per minute). It leaves the list's order alone.`

```bash
git add src/schemas/chat.py src/api/routes/chat.py tests/test_chat.py tests/test_rate_limits.py CHANGELOG.md
git commit -m "Rename a thread without moving it up the list"
```

### Task A2: Citation ids and content hashes

**Files:**
- Create: `migrations/versions/20260926_1200-9c1e4b7a2d10_add_message_source_content_hash.py`
- Create: `src/services/passages.py`. This task adds only `content_hash`; Task A3 fills in the rest.
- Modify: `src/models/chat.py` (`MessageSource`)
- Modify: `src/schemas/chat.py` (`SourceResponse`)
- Modify: `src/api/routes/chat.py`: add `_context` and `_save_answer`, and use them in `create_message`.
- Test: `tests/test_chat.py`, `tests/test_models_chat.py`

**Interfaces:**
- Produces:
  - `passages.content_hash(text: str) -> str`: the SHA-256 hex digest.
  - `MessageSource.content_sha256: str | None`.
  - `SourceResponse.id: uuid.UUID`.
- Produces (route module, private, reused by A6):
  - `_context(db, thread) -> tuple[list[dict], tuple[ShownPlan, ...]]`.
  - `_save_answer(db, thread, question: str, result: Answer) -> Message`.

- [ ] **Step 1: Write the failing tests** (`tests/test_chat.py`)

```python
import hashlib

from src.models.chat import MessageSource


@patch("src.api.routes.chat.answer_query")
def test_sources_carry_an_id_and_the_passage_hash(mock_answer_query, client):
    mock_answer_query.return_value = Answer("A deductible is what you pay first.", _fake_chunks())
    headers = _auth_headers(client, email="hash@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]

    sent = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "Deductible?"}, headers=headers)

    source = sent.get_json()["sources"][0]
    assert uuid.UUID(source["id"])
    reopened = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assert next(m for m in reopened if m["role"] == "assistant")["sources"][0]["id"] == source["id"]
    from src.api import deps as api_deps  # the test's shared session
    row = api_deps.SessionLocal().get(MessageSource, uuid.UUID(source["id"]))
    assert row.content_sha256 == hashlib.sha256("A deductible is...".encode()).hexdigest()
```

In `tests/test_models_chat.py`, add a test that a `MessageSource` saves with
`content_sha256=None`. Follow the file's existing `session` fixture style.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_chat.py -k hash -q`
Expected: FAIL with `KeyError: 'id'`.

- [ ] **Step 3: Implement**

The migration: `down_revision = "3b1d6e2a9c47"`, `revision = "9c1e4b7a2d10"`.
Its header docstring follows the last migration's shape.

```python
def upgrade() -> None:
    # The passage text an answer used, hashed, so a rebuilt chunk that now says
    # something else is never shown as what was cited (ADR 0007, 0027). Older
    # citations stay NULL: "unverified".
    op.add_column("message_sources", sa.Column("content_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("message_sources", "content_sha256")
```

In `MessageSource`:

```python
    # SHA-256 of the passage text as the answer used it; NULL on citations saved
    # before ADR 0027. How the passage endpoint tells a rebuilt chunk apart.
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

In `SourceResponse`, add `id: uuid.UUID` as its first field.

Then `src/services/passages.py`:

```python
"""Cited passages, as the Sources panel shows them (ADR 0027)."""
import hashlib


def content_hash(text: str) -> str:
    """The passage text's fingerprint, stored with each citation."""
    return hashlib.sha256(text.encode()).hexdigest()
```

In `src/api/routes/chat.py`, lift the history and shown-plans lines, and the
assistant-message block, out of `create_message` into helpers. Then have
`create_message` call them:

```python
def _context(db, thread) -> tuple[list[dict], tuple[ShownPlan, ...]]:
    """The thread's history and last-shown plans, read before the new question is added."""
    prior = db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    ).scalars().all()
    return [{"role": m.role, "content": m.content} for m in prior], _shown_plans(db, thread.id)


def _save_answer(db, thread, question: str, result) -> Message:
    """The assistant message with its citations and plan snapshots (ADR 0007, 0011)."""
    message = Message(
        thread_id=thread.id,
        role="assistant",
        content=result.text,
        sources=[
            MessageSource(chunk_id=c.chunk_id, source=c.source, relevance=c.score,
                          content_sha256=content_hash(c.content))
            for c in result.chunks
        ],
        plans=[_plan_row(position, plan) for position, plan in enumerate(result.plans)],
    )
    db.add(message)
    db.flush()
    if thread.title is None:
        thread.title = question[:80]
    return message
```

The body of `create_message` then reads:
`history, shown_plans = _context(db, thread)` … and, after the answer,
`assistant_message = _save_answer(db, thread, body.content, result)`.

- [ ] **Step 4: Run the tests and confirm they pass; check the migration**

Run:
```bash
make migrate && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check
uv run pytest tests/test_chat.py tests/test_models_chat.py tests/test_token_budget.py -q
```
Expected: `alembic check` reports no new upgrade operations, and all tests
PASS.

- [ ] **Step 5: CHANGELOG and commit**

Add these bullets under `### Added`:
- `Each citation now carries its id, and a SHA-256 of the passage text it used (migration 9c1e4b7a2d10).`

```bash
git add migrations/versions/*9c1e4b7a2d10* src/models/chat.py src/schemas/chat.py src/api/routes/chat.py src/services/passages.py tests/test_chat.py tests/test_models_chat.py CHANGELOG.md
git commit -m "Give each citation an id and a hash of the passage it used"
```

### Task A3: The passages service (excerpt and source kinds)

**Files:**
- Create: `src/core/urls.py`, holding `unsafe_reason`, moved here.
- Modify: `src/ingestion/sbc/fetch.py`: `from src.core.urls import unsafe_reason`, keeping the name importable from `fetch`.
- Modify: `src/ingestion/sources/registry.py`: add a public `registered(source_id)`.
- Modify: `src/services/passages.py`
- Test: create `tests/test_passages.py`; the existing `tests/test_sbc_fetch.py` must stay green.

**Interfaces:**
- Consumes: `content_hash` (A2).
- Produces:
  - `passages.EXCERPT_CHARS = 300`.
  - `passages.excerpt(passage: str, answer_text: str, limit: int = EXCERPT_CHARS) -> str`.
  - `passages.Passage`: a frozen dataclass with `kind, title, document, section,
    quote, status, url, license`. `license` is `dict | None` with keys `name` and
    `url`.
  - `passages.passage_for(db, chunk_id: str, label: str, stored_hash: str | None, answer_text: str) -> Passage`.
  - `registry.registered(source_id: str) -> RegisteredSource | None`.
  - `src.core.urls.unsafe_reason(url: str) -> str | None`.

- [ ] **Step 1: Write the failing tests** (`tests/test_passages.py`)

```python
from src.models.chunk import Chunk
from src.models.sbc import SbcChunk, SbcDocument
from src.services.passages import EXCERPT_CHARS, content_hash, excerpt, passage_for

LONG = ("Emergency room care | $400 copay/visit; deductible does not apply | Cost sharing waived if admitted.\n"
        "Emergency medical transportation | $250 copay/trip; deductible does not apply | None\n"
        "Urgent care | $50 copay/visit; deductible does not apply | $50 copay/visit; deductible does not apply\n"
        "Hospital stay | 30% coinsurance | Preauthorization is required for non-emergency services.")


def test_a_short_passage_is_returned_whole():
    assert excerpt("Copayment: A fixed amount you pay.", "anything") == "Copayment: A fixed amount you pay."


def test_the_excerpt_starts_at_the_segment_most_like_the_answer():
    text = excerpt(LONG, "It charges a $50 copay per urgent care visit.")
    assert text.startswith("… Urgent care | $50 copay/visit")
    assert len(text.removeprefix("… ").removesuffix(" …")) <= EXCERPT_CHARS


def test_ties_go_to_the_earlier_segment():
    assert excerpt(LONG, "nothing in common here").startswith("Emergency room care")


def test_a_cut_excerpt_is_marked_at_the_end():
    assert excerpt(LONG, "Emergency room care").endswith(" …")


def test_a_single_long_segment_is_cut_at_a_space():
    words = " ".join(["deductible"] * 60)
    text = excerpt(words, "deductible")
    body = text.removesuffix(" …")
    assert len(body) <= EXCERPT_CHARS and not body.endswith(" ") and text.endswith(" …")


def test_empty_inputs():
    assert excerpt("", "x") == ""
    assert excerpt(LONG, "").startswith("Emergency room care")


def _sbc(session, url="https://www.sharphealthplan.com/docs/sbc.pdf"):
    doc = SbcDocument(url=url, plan_year=2026, status="ok", title="Sharp Health Plan: Sharp Silver 70 Premier HMO")
    session.add(doc)
    session.flush()
    session.add(SbcChunk(document_id=doc.id, chunk_id="sbc_2026_abc_s11_c00", section="If you need immediate medical attention",
                         position=0, content=LONG))
    session.flush()


SBC_LABEL = "Sharp Silver 70 Premier HMO - Summary of Benefits - If you need immediate medical attention.pdf"


def test_an_sbc_passage(session):
    _sbc(session)
    p = passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, content_hash(LONG), "urgent care $50")
    assert (p.kind, p.title, p.document, p.section, p.status) == (
        "sbc", "Sharp Silver 70 Premier HMO", "Summary of Benefits and Coverage, 2026",
        "If you need immediate medical attention", "ok")
    assert p.url == "https://www.sharphealthplan.com/docs/sbc.pdf" and p.license is None
    assert "Urgent care" in p.quote


def test_an_unsafe_document_url_is_dropped(session):
    _sbc(session, url="http://www.sharphealthplan.com/docs/sbc.pdf")
    assert passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, None, "").url is None


def test_statuses(session):
    _sbc(session)
    assert passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, None, "").status == "unverified"
    changed = passage_for(session, "sbc_2026_abc_s11_c00", SBC_LABEL, content_hash("other text"), "")
    assert (changed.status, changed.quote) == ("changed", None)
    missing = passage_for(session, "sbc_2026_gone_s01_c00", SBC_LABEL, None, "")
    assert (missing.status, missing.quote, missing.title) == ("missing", None, "Sharp Silver 70 Premier HMO")


def test_a_wikipedia_passage_is_credited_from_the_registry(session):
    session.add(Chunk(chunk_id="wikipedia_Health_insurance_s0_c00", source="wiki_Health_insurance.txt",
                      content="Health insurance covers medical expenses.", embedding=[0.0] * 384))
    session.flush()
    p = passage_for(session, "wikipedia_Health_insurance_s0_c00", "wiki_Health_insurance.txt", None, "")
    assert (p.kind, p.title, p.document) == ("wikipedia", "Health insurance", "Wikipedia article")
    assert p.url == "https://en.wikipedia.org/wiki/Health_insurance"
    assert p.license == {"name": "CC BY-SA 4.0", "url": "https://creativecommons.org/licenses/by-sa/4.0/"}


def test_a_healthcare_gov_passage(session):
    session.add(Chunk(chunk_id="healthcare_gov_glossary_Copayment_s0_c00", source="hcg_glossary_Copayment.md",
                      content="Copayment: A fixed amount you pay for a plan-covered service, like $30.", embedding=[0.0] * 384))
    session.flush()
    p = passage_for(session, "healthcare_gov_glossary_Copayment_s0_c00", "hcg_glossary_Copayment.md", None, "")
    assert (p.kind, p.title, p.document, p.url, p.license) == (
        "healthcare_gov", "Copayment", "HealthCare.gov glossary", None, None)
```

Check the `SbcDocument` required columns against `src/models/sbc.py`. If
`status` or `title` differ, pass whatever the model requires. Take the
embedding width from `settings.embedding_dim` rather than hard-coding 384:
`from src.policypal.config import settings`, then
`[0.0] * settings.embedding_dim`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_passages.py -q`
Expected: FAIL with `ImportError: cannot import name 'excerpt'`.

- [ ] **Step 3: Implement**

`src/core/urls.py`: move the body of `unsafe_reason` verbatim from
`src/ingestion/sbc/fetch.py:156-168`, with its `ipaddress` and `urlsplit`
imports. In `fetch.py`, delete the function and add `from src.core.urls import
unsafe_reason  # re-exported: callers import it from here`.

`registry.py`:

```python
def registered(source_id: str) -> RegisteredSource | None:
    """The committed registry's entry for `source_id`, enabled or not."""
    return _committed().get(source_id)
```

Complete `src/services/passages.py`:

```python
"""Cited passages, as the Sources panel shows them (ADR 0027).

A quote is brief (ADR 0013: SBC text is quoted, never redistributed) and is
the part of the passage most like the answer that cited it. Every field is
derived here, by the server, never taken from model output.
"""
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.urls import unsafe_reason
from src.ingestion.sources.registry import registered
from src.models.chunk import Chunk
from src.models.sbc import SbcChunk, SbcDocument

EXCERPT_CHARS = 300
_SBC_SEPARATOR = " - Summary of Benefits - "
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    "the and for are but not you your with this that from have has was were will can its any all per may out".split()
)


@dataclass(frozen=True)
class Passage:
    kind: str                 # sbc | wikipedia | healthcare_gov | other
    title: str
    document: str | None
    section: str | None
    quote: str | None
    status: str               # ok | unverified | changed | missing
    url: str | None
    license: dict | None      # {"name", "url"}


def content_hash(text: str) -> str:
    """The passage text's fingerprint, stored with each citation."""
    return hashlib.sha256(text.encode()).hexdigest()


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if (len(w) >= 3 or w.isdigit()) and w not in _STOP_WORDS}


def _segments(text: str) -> list[str]:
    return [s.strip() for line in text.splitlines() for s in _SENTENCE_END.split(line) if s.strip()]


def excerpt(passage: str, answer_text: str, limit: int = EXCERPT_CHARS) -> str:
    """At most `limit` characters of `passage`, starting where it best matches the answer."""
    text = passage.strip()
    if len(text) <= limit:
        return text
    segments = _segments(text)
    wanted = _words(answer_text)
    best = max(range(len(segments)), key=lambda i: (len(_words(segments[i]) & wanted), -i))

    chosen: list[str] = []
    length = 0
    for segment in segments[best:]:
        added = len(segment) + (1 if chosen else 0)
        if length + added > limit:
            break
        chosen.append(segment)
        length += added

    if chosen:
        body = " ".join(chosen)
        reaches_end = best + len(chosen) == len(segments)
    else:
        cut = segments[best][:limit]
        body = cut.rsplit(" ", 1)[0] if " " in cut else cut
        reaches_end = False
    return ("… " if best > 0 else "") + body + ("" if reaches_end else " …")


def _safe(url: str | None) -> str | None:
    return url if url and unsafe_reason(url) is None else None


def _stem(label: str) -> str:
    return label.rsplit(".", 1)[0] if "." in label else label


def _corpus_fields(label: str) -> tuple[str, str, str | None, str | None, dict | None]:
    """kind, title, document, url, license for a general-corpus label (ADR 0003)."""
    stem = _stem(label)
    if stem.startswith("wiki_"):
        title = stem.removeprefix("wiki_")
        entry = registered("wikipedia")
        license_ = {"name": entry.license, "url": entry.license_url} if entry else None
        url = "https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_"))
        return "wikipedia", title.replace("_", " "), "Wikipedia article", url, license_
    for prefix, document in (("hcg_glossary_", "HealthCare.gov glossary"), ("hcg_article_", "HealthCare.gov article")):
        if stem.startswith(prefix):
            return "healthcare_gov", stem.removeprefix(prefix).replace("_", " "), document, None, None
    return "other", stem, None, None, None


def _status(text: str | None, stored_hash: str | None) -> str:
    if text is None:
        return "missing"
    if stored_hash is None:
        return "unverified"
    return "ok" if content_hash(text) == stored_hash else "changed"


def passage_for(db: Session, chunk_id: str, label: str, stored_hash: str | None, answer_text: str) -> Passage:
    """The citation `label` → `chunk_id`, as it can be shown now."""
    if chunk_id.startswith("sbc_"):
        row = db.execute(
            select(SbcChunk.content, SbcDocument.url, SbcDocument.plan_year)
            .join(SbcDocument, SbcDocument.id == SbcChunk.document_id)
            .where(SbcChunk.chunk_id == chunk_id)
        ).first()
        plan, _, section = _stem(label).partition(_SBC_SEPARATOR)
        text = row.content if row else None
        document = f"Summary of Benefits and Coverage, {row.plan_year}" if row else "Summary of Benefits and Coverage"
        kind, title, url, license_ = "sbc", plan.strip(), _safe(row.url if row else None), None
        section = section.strip() or None
    else:
        text = db.scalar(select(Chunk.content).where(Chunk.chunk_id == chunk_id))
        kind, title, document, url, license_ = _corpus_fields(label)
        section = None

    status = _status(text, stored_hash)
    shown = excerpt(text, answer_text) if status in ("ok", "unverified") else None
    return Passage(kind, title, document, section, shown, status, url, license_)
```

`_stem` drops only the trailing extension. SBC labels always end in `.pdf`
(`plan_coverage.source_label`), so the section is recovered exactly.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_passages.py tests/test_sbc_fetch.py tests/test_sbc_manifest.py tests/test_registry.py -q`
Expected: all PASS.

- [ ] **Step 5: CHANGELOG and commit**

Add this bullet under `### Added`:
- `The passages service turns a citation into a brief quote (≤300 characters, the part most like the answer), with its source, link and licence.`

Add this one under `### Changed`:
- `\`unsafe_reason\` moved to \`src/core/urls.py\`.`

```bash
git add src/core/urls.py src/ingestion/sbc/fetch.py src/ingestion/sources/registry.py src/services/passages.py tests/test_passages.py CHANGELOG.md
git commit -m "Quote a cited passage briefly, with its source and licence"
```

### Task A4: The source lookup endpoint

**Files:**
- Modify: `src/schemas/chat.py`: add `PassageLicense` and `PassageResponse`.
- Modify: `src/api/routes/chat.py`: add `get_source`.
- Test: `tests/test_chat.py`, `tests/test_rate_limits.py`

**Interfaces:**
- Consumes: `passage_for` (A3), `MessageSource.content_sha256` (A2).
- Produces: `GET /api/chat/sources/<source_id>`, returning a `PassageResponse`
  JSON with the spec's fields and an `id`.

- [ ] **Step 1: Write the failing tests** (`tests/test_chat.py`)

```python
def _one_source(client, email, chunks=None):
    headers = _auth_headers(client, email=email)
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    with patch("src.api.routes.chat.answer_query", return_value=Answer("Health insurance covers costs.", chunks or [
        RetrievedChunk(chunk_id="wikipedia_T_s0_c00", content="Health insurance covers medical expenses.",
                       source="wiki_Health_insurance.txt", score=0.88)])):
        sent = client.post(f"/api/chat/threads/{thread_id}/messages", json={"content": "What is it?"}, headers=headers)
    return headers, sent.get_json()["sources"][0]["id"]


def test_a_source_reads_as_missing_when_its_chunk_is_gone(client):
    headers, source_id = _one_source(client, "src-missing@example.com")

    resp = client.get(f"/api/chat/sources/{source_id}", headers=headers)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == source_id
    assert (body["kind"], body["title"], body["status"], body["quote"]) == ("wikipedia", "Health insurance", "missing", None)
    assert body["license"]["name"] == "CC BY-SA 4.0"


def test_a_source_quotes_its_chunk(client):
    from src.api import deps as api_deps
    db = api_deps.SessionLocal()
    db.add(Chunk(chunk_id="wikipedia_T_s0_c00", source="wiki_Health_insurance.txt",
                 content="Health insurance covers medical expenses.", embedding=[0.0] * settings.embedding_dim))
    db.flush()
    headers, source_id = _one_source(client, "src-ok@example.com")

    body = client.get(f"/api/chat/sources/{source_id}", headers=headers).get_json()

    assert (body["status"], body["quote"]) == ("ok", "Health insurance covers medical expenses.")


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
```

Add `from src.models.chunk import Chunk` and `from src.policypal.config import
settings` to the imports. For the rate-limit test in `tests/test_rate_limits.py`,
hammer `GET /api/chat/sources/00000000-0000-0000-0000-000000000000` 61 times.
The first 60 are 404, and the 61st is 429 with `Retry-After`: a 404 counts
towards the limit, as the file's existing tests show.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_chat.py -k source -q`
Expected: FAIL (404 for every lookup, since the route doesn't exist).

- [ ] **Step 3: Implement**

`src/schemas/chat.py`:

```python
class PassageLicense(BaseModel):
    name: str
    url: str


class PassageResponse(BaseModel):
    """A cited passage as it can be shown now (ADR 0027)."""

    id: uuid.UUID
    kind: str
    title: str
    document: str | None
    section: str | None
    quote: str | None
    status: str
    url: str | None
    license: PassageLicense | None
```

`src/api/routes/chat.py`:

```python
@bp.get("/sources/<source_id>")
@jwt_required()
@limiter.limit("60 per minute")
def get_source(source_id: str):
    """One of the current user's citations, quoted briefly. Addressed by the
    citation's own id, never by chunk id: chunk ids are guessable (ADR 0027)."""
    db = get_db()
    user = get_current_user()
    try:
        parsed_id = uuid.UUID(source_id)
    except ValueError:
        abort(404)

    row = db.execute(
        select(MessageSource, Message.content)
        .join(Message, Message.id == MessageSource.message_id)
        .join(Thread, Thread.id == Message.thread_id)
        .where(MessageSource.id == parsed_id, Thread.user_id == user.id)
    ).first()
    if row is None:
        abort(404)

    source, answer_text = row
    passage = passage_for(db, source.chunk_id, source.source, source.content_sha256, answer_text)
    response = PassageResponse(id=source.id, **dataclasses.asdict(passage))
    return jsonify(response.model_dump(mode="json"))
```

Import `dataclasses`, `passage_for` and `PassageResponse`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_chat.py tests/test_rate_limits.py -q`
Expected: all PASS.

- [ ] **Step 5: CHANGELOG and commit**

`- \`GET /api/chat/sources/<id>\` returns one of your citations as a brief quote: ok, unverified (older answers), changed or missing (60 per minute; another user's citation is 404).`

```bash
git add src/schemas/chat.py src/api/routes/chat.py tests/test_chat.py tests/test_rate_limits.py CHANGELOG.md
git commit -m "Show a citation's passage to the user who was answered with it"
```

### Task A5: Streaming generation events

**Files:**
- Modify: `src/services/generation.py`
- Test: `tests/test_generation.py`

**Interfaces:**
- Produces:
  - The frozen dataclasses `Stage(name: str)`, `Notice(text: str)`,
    `Delta(text: str)`, `Reset()` and `Done(answer: Answer)`.
  - `answer_events(query, chunks, history=None, profile=None, shown_plans=(), *, stream=False) -> Iterator[event]`.
    The last event is always `Done`.
  - `answer_query_events(query, history=None, top_k=None, profile=None, shown_plans=(), *, stream=True) -> Iterator[event]`.
  - `answer()` and `answer_query()` keep their signatures and return values
    exactly. **`answer_query` stays as it is (it calls `answer`), because
    `tests/test_generation.py:294,305` patches `generation.answer`.**

- [ ] **Step 1: Write the failing tests** (append to `tests/test_generation.py`)

```python
from src.services.generation import Delta, Done, Notice, Reset, Stage, answer_events, answer_query_events


def _chunk(content=None, tool_calls=None, finish=None, usage=None):
    """One streamed chunk, shaped like the SDK's ChatCompletionChunk."""
    choices = [] if content is None and tool_calls is None and finish is None else [SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=tool_calls), finish_reason=finish)]
    return SimpleNamespace(choices=choices, usage=usage)


def _tool_delta(index, call_id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=call_id,
                           function=SimpleNamespace(name=name, arguments=arguments))


def _streaming_client(*rounds):
    client = MagicMock()
    client.chat.completions.create.side_effect = [iter(r) for r in rounds]
    return client


def _events(gen):
    return list(gen)


def test_streamed_answer_matches_the_blocking_one():
    chunks = [RetrievedChunk("c1", "A deductible is the amount you pay first.", "wiki_D.txt", 0.9)]
    rounds = [_chunk("A deductible "), _chunk("is what you pay first."), _chunk(finish="stop"),
              _chunk(usage=SimpleNamespace(total_tokens=42))]
    with patch("src.services.generation._llm", return_value=_streaming_client(rounds)):
        reset_token_usage()
        events = _events(answer_events("What is a deductible?", chunks, stream=True))
    assert events[0] == Stage("writing")
    assert [e.text for e in events if isinstance(e, Delta)] == ["A deductible ", "is what you pay first."]
    assert events[-1] == Done(Answer("A deductible is what you pay first.", chunks))
    assert token_usage() == 42


def test_reset_when_a_streamed_round_calls_a_tool(_no_plan_catalog):
    _no_plan_catalog.return_value = True
    chunks = [RetrievedChunk("c1", "context", "wiki_D.txt", 0.9)]
    first = [_chunk("Let me look"), _chunk(tool_calls=[_tool_delta(0, "call_1", "search_plans", '{"zip_code": ')]),
             _chunk(tool_calls=[_tool_delta(0, arguments=_ARGS.removeprefix('{"zip_code": '))]),
             _chunk(finish="tool_calls"), _chunk(usage=SimpleNamespace(total_tokens=5))]
    second = [_chunk("Here are the plans."), _chunk(finish="stop"), _chunk(usage=SimpleNamespace(total_tokens=7))]
    with patch("src.services.generation._llm", return_value=_streaming_client(first, second)), \
         patch("src.services.generation.run_tool", return_value=_plan_found()) as run_tool:
        events = _events(answer_events("Silver plans?", chunks, stream=True))
    kinds = [type(e).__name__ for e in events]
    assert kinds.index("Reset") > kinds.index("Delta")
    assert Stage("plans") in events
    assert run_tool.call_args.args[1] == _ARGS          # fragments reassembled
    assert events[-1].answer.text.endswith("Here are the plans.")


def test_nothing_streams_before_the_answer_is_grounded(_no_plan_catalog):
    _no_plan_catalog.return_value = True
    rounds = [_chunk("Ungrounded guess."), _chunk(finish="stop"), _chunk(usage=SimpleNamespace(total_tokens=3))]
    with patch("src.services.generation._llm", return_value=_streaming_client(rounds)):
        events = _events(answer_events("Hi", [], stream=True))
    assert not any(isinstance(e, Delta) for e in events)
    assert events[-1].answer.text == NO_ANSWER_RESPONSE


def test_a_notice_is_sent_as_soon_as_a_tool_returns_it(_no_plan_catalog):
    _no_plan_catalog.return_value = True
    outcome = replace(_plan_found(), notice="These are 2026 plans.")
    first = [_chunk(tool_calls=[_tool_delta(0, "call_1", "search_plans", _ARGS)]), _chunk(finish="tool_calls")]
    second = [_chunk("Plans."), _chunk(finish="stop")]
    with patch("src.services.generation._llm", return_value=_streaming_client(first, second)), \
         patch("src.services.generation.run_tool", return_value=outcome):
        events = _events(answer_events("Plans?", [RetrievedChunk("c", "x", "wiki_X.txt", 0.9)], stream=True))
    assert events.index(Notice("These are 2026 plans.")) < next(i for i, e in enumerate(events) if isinstance(e, Delta))
    assert events[-1].answer.text.startswith("These are 2026 plans.")


def test_a_stream_without_usage_is_warned_about(caplog):
    rounds = [_chunk("Text."), _chunk(finish="stop")]
    with patch("src.services.generation._llm", return_value=_streaming_client(rounds)):
        _events(answer_events("Q", [RetrievedChunk("c", "x", "wiki_X.txt", 0.9)], stream=True))
    assert "no usage" in caplog.text


def test_answer_query_events_reports_rewriting_and_searching():
    history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Reply"}]
    with patch("src.services.generation.rewrite_query", return_value="standalone"), \
         patch("src.services.generation.search", return_value=[]) as search, \
         patch("src.services.generation.answer_events", return_value=iter([Done(Answer("x", []))])):
        events = _events(answer_query_events("And?", history))
    assert events[:2] == [Stage("understanding"), Stage("searching")]
    search.assert_called_once_with("standalone", None)
```

If `_plan_found()` returns something other than a `ToolOutcome`, use the
existing helper that does, as its current tests do. `replace` comes from
`dataclasses`.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_generation.py -q -k "stream or reset or grounded or notice or usage or answer_query_events"`
Expected: FAIL with `ImportError: cannot import name 'Delta'`.

- [ ] **Step 3: Implement** (in `src/services/generation.py`)

Add these after `Answer`:

```python
@dataclass(frozen=True)
class Stage:
    """Progress, for the user: understanding | searching | plans | coverage | writing."""
    name: str


@dataclass(frozen=True)
class Notice:
    """A server-written notice, sent as soon as a tool returns it (ADR 0024, 0026)."""
    text: str


@dataclass(frozen=True)
class Delta:
    text: str


@dataclass(frozen=True)
class Reset:
    """Discard the deltas so far: the round that streamed them went on to call a tool."""


@dataclass(frozen=True)
class Done:
    answer: Answer
```

Next to `_complete`, add:

```python
def _blocking(messages, max_output_tokens, model, *, tools=None, tool_choice=None):
    """_complete as a generator that yields no text, so both paths share one loop."""
    return _complete(messages, max_output_tokens, model, tools=tools, tool_choice=tool_choice)
    yield  # unreachable: makes this a generator


def _complete_stream(messages, max_output_tokens, model, *, tools=None, tool_choice=None):
    """Call the model once, streaming: yields text as it arrives and returns the
    whole message (content and tool calls), as _complete does."""
    options = {}
    if tools:
        options = {"tools": tools, "parallel_tool_calls": False}
        if tool_choice:
            options["tool_choice"] = tool_choice
    stream = _llm().chat.completions.create(
        model=model,
        messages=messages,
        max_completion_tokens=max_output_tokens,
        reasoning_effort=settings.reasoning_effort,
        stream=True,
        stream_options={"include_usage": True},
        **options,
    )

    parts: list[str] = []
    calls: dict[int, dict] = {}
    finish_reason = None
    counted = False
    for chunk in stream:
        if chunk.usage:
            _tokens_used.set(_tokens_used.get() + chunk.usage.total_tokens)
            counted = True
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.delta.content:
            parts.append(choice.delta.content)
            yield choice.delta.content
        for piece in choice.delta.tool_calls or []:
            call = calls.setdefault(piece.index, {"id": None, "name": "", "arguments": ""})
            call["id"] = piece.id or call["id"]
            if piece.function:
                call["name"] += piece.function.name or ""
                call["arguments"] += piece.function.arguments or ""
        finish_reason = choice.finish_reason or finish_reason

    if not counted:
        logger.warning("streamed completion for %s returned no usage; spend uncounted", model)
    if finish_reason not in ("stop", "tool_calls"):
        logger.warning("completion for %s finished with reason %r, not 'stop'", model, finish_reason)
    tool_calls = [
        SimpleNamespace(id=c["id"], function=SimpleNamespace(name=c["name"], arguments=c["arguments"]))
        for _, c in sorted(calls.items())
    ]
    return SimpleNamespace(content="".join(parts) or None, tool_calls=tool_calls or None)
```

Rename the body of `answer` into `answer_events`, with these changes and
nothing else:

```python
def answer_events(query: str, chunks: list[RetrievedChunk],
                  history: list[dict] | None = None, profile: PlanProfile | None = None,
                  shown_plans: tuple[ShownPlan, ...] = (), *, stream: bool = False) -> Iterator:
    """answer(), as events: Stage, Notice, Delta and Reset as they happen, then Done.

    Text is forwarded only once the answer is grounded (chunks retrieved, or a
    tool run), so the NO_ANSWER path never has to take back shown text.
    """
    plan_tools = plan_catalog_available()
    if not chunks and not plan_tools:
        yield Done(Answer(NO_ANSWER_RESPONSE, chunks))
        return
    # … the existing setup, unchanged …
    complete = _complete_stream if stream else _blocking
    writing = False
    last_stage = None

    for round_ in range(_MAX_TOOL_ROUNDS + 1):
        last = round_ == _MAX_TOOL_ROUNDS
        grounded = bool(chunks) or searched
        streamed = False
        pieces = complete(messages, cap, settings.llm_model, tools=tools,
                          tool_choice="none" if tools and last else None)
        while True:
            try:
                piece = next(pieces)
            except StopIteration as finished:
                message = finished.value
                break
            if grounded:
                if not writing:
                    writing = True
                    yield Stage("writing")
                streamed = True
                yield Delta(piece)
        calls = (getattr(message, "tool_calls", None) or []) if tools and not last else []
        if not calls:
            break
        if streamed:
            yield Reset()
            writing = False

        messages.append(_assistant_turn(message, calls))
        for call in calls:
            stage = "plans" if call.function.name == SEARCH_PLANS else "coverage"
            if stage != last_stage:
                last_stage = stage
                yield Stage(stage)
            outcome = run_tool(call.function.name, call.function.arguments, profile, dict(plan_years))
            # … the existing bookkeeping, unchanged, except the notice: …
            if outcome.notice and outcome.notice not in notices:
                notices.append(outcome.notice)
                yield Notice(outcome.notice)
            # … the existing tool message append, unchanged …
        cap = settings.plan_answer_max_output_tokens

    # … the existing post-processing, unchanged; each `return Answer(...)`
    # becomes `yield Done(Answer(...)); return` …


def _final(events) -> Answer:
    for event in events:
        if isinstance(event, Done):
            return event.answer
    raise RuntimeError("answer_events ended without Done")


def answer(query: str, chunks: list[RetrievedChunk],
           history: list[dict] | None = None, profile: PlanProfile | None = None,
           shown_plans: tuple[ShownPlan, ...] = ()) -> Answer:
    """Answer from the retrieved chunks and, when the catalog is loaded, plan searches."""
    return _final(answer_events(query, chunks, history, profile, shown_plans))


def answer_query_events(query: str, history: list[dict] | None = None, top_k: int | None = None,
                        profile: PlanProfile | None = None, shown_plans: tuple[ShownPlan, ...] = (),
                        *, stream: bool = True) -> Iterator:
    """answer_query(), as events, for the streaming route (ADR 0027)."""
    selected = select_history(history or [])
    if selected:
        yield Stage("understanding")
    retrieval_query = rewrite_query(query, selected)
    yield Stage("searching")
    chunks = search(retrieval_query, top_k)
    yield from answer_events(query, chunks, selected, profile, shown_plans, stream=stream)
```

Add these imports: `from collections.abc import Iterator`, `from types import
SimpleNamespace`, and `SEARCH_PLANS` from `.tools`. Keep `answer_query`
exactly as it is.

**Also check the existing tests.** Current tests build `_completion(...)`
messages from `SimpleNamespace(content=..., tool_calls=...)`. `_blocking`
returns what `_complete` returns, so they pass unchanged.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_generation.py tests/test_tools.py -q`
Expected: all PASS, the pre-existing tests included.

- [ ] **Step 5: CHANGELOG and commit**

`- Generation is an event stream (stages, notices, text, reset, done); \`answer()\` and \`answer_query()\` are unchanged wrappers.`

```bash
git add src/services/generation.py tests/test_generation.py CHANGELOG.md
git commit -m "Generate an answer as events, streaming only its grounded text"
```

### Task A6: The streaming route

**Files:**
- Modify: `src/api/routes/chat.py`
- Test: create `tests/test_chat_stream.py`; also `tests/test_rate_limits.py`

**Interfaces:**
- Consumes: `answer_query_events`, `Stage`, `Notice`, `Delta`, `Reset` and
  `Done` (A5); `_context` and `_save_answer` (A2).
- Produces: `POST /api/chat/threads/<id>/messages/stream`, returning
  `text/event-stream` with the spec's events.

- [ ] **Step 1: Write the failing tests** (`tests/test_chat_stream.py`)

```python
import json
from unittest.mock import patch

import openai
import pytest

from src.services.generation import Answer, Delta, Done, Notice, Reset, Stage
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


def _stream(client, headers, thread_id, events, content="What is a deductible?"):
    with patch("src.api.routes.chat.answer_query_events", return_value=iter(events)):
        return client.post(f"/api/chat/threads/{thread_id}/messages/stream", json={"content": content}, headers=headers)


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
    done = events[-1][1]
    assert done["message"]["content"] == answer.text
    assert done["message"]["sources"][0]["id"]
    assert done["thread"]["title"] == "What is a deductible?"
    saved = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assert [m["role"] for m in saved] == ["user", "assistant"]
    assert saved[1] == done["message"]
    assert saved[0]["id"] == events[0][1]["message"]["id"]


def test_reset_is_forwarded(client):
    headers, thread_id = _thread(client, "stream-reset@example.com")
    events = _events(_stream(client, headers, thread_id, [Delta("x"), Reset(), Done(Answer("y", CHUNKS))]))
    assert [e for e, _ in events] == ["user_message", "delta", "reset", "done"]


def test_errors_before_the_stream_are_json(client):
    headers, thread_id = _thread(client, "stream-pre@example.com")
    missing = client.post("/api/chat/threads/00000000-0000-0000-0000-000000000000/messages/stream",
                          json={"content": "x"}, headers=headers)
    invalid = client.post(f"/api/chat/threads/{thread_id}/messages/stream", json={"content": ""}, headers=headers)
    assert (missing.status_code, missing.mimetype) == (404, "application/json")
    assert (invalid.status_code, invalid.mimetype) == (422, "application/json")


def test_an_exhausted_budget_is_a_json_429(client):
    headers, thread_id = _thread(client, "stream-budget@example.com")
    with patch("src.api.routes.chat.budget_exhausted", return_value=True):
        resp = client.post(f"/api/chat/threads/{thread_id}/messages/stream", json={"content": "x"}, headers=headers)
    assert resp.status_code == 429 and resp.get_json()["error"] == "daily token budget exhausted"
    assert "Retry-After" in resp.headers


def _failing():
    yield Stage("searching")
    raise openai.APIConnectionError(request=None)


def test_a_model_failure_ends_with_error_and_keeps_the_question(client):
    headers, thread_id = _thread(client, "stream-fail@example.com")
    with patch("src.api.routes.chat.answer_query_events", return_value=_failing()), \
         patch("src.api.routes.chat.token_usage", return_value=11), \
         patch("src.api.routes.chat.record_tokens") as record:
        resp = client.post(f"/api/chat/threads/{thread_id}/messages/stream", json={"content": "x"}, headers=headers)
        events = _events(resp)
    assert events[-1] == ("error", {"error": "generation failed"})
    record.assert_called_once()
    assert record.call_args.args[2] == 11
    saved = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assert [m["role"] for m in saved] == ["user"]


def test_disconnect_records_spend_once_and_saves_no_answer(client):
    headers, thread_id = _thread(client, "stream-drop@example.com")

    def slow():
        yield Stage("searching")
        yield Delta("partial")
        yield Done(Answer("never saved", CHUNKS))

    with patch("src.api.routes.chat.answer_query_events", return_value=slow()), \
         patch("src.api.routes.chat.token_usage", return_value=9), \
         patch("src.api.routes.chat.record_tokens") as record:
        resp = client.post(f"/api/chat/threads/{thread_id}/messages/stream", json={"content": "x"},
                           headers=headers, buffered=False)
        stream = iter(resp.response)
        next(stream)              # user_message
        next(stream)              # stage
        resp.close()              # the client goes away
    record.assert_called_once()
    saved = client.get(f"/api/chat/threads/{thread_id}/messages", headers=headers).get_json()
    assert [m["role"] for m in saved] == ["user"]
```

In `tests/test_rate_limits.py`:

```python
def test_both_send_routes_share_one_limit(client):
    headers = _auth_headers(client, "send-shared@example.com")
    thread_id = client.post("/api/chat/threads", json={}, headers=headers).get_json()["id"]
    body = {"content": "x"}
    with patch("src.api.routes.chat.answer_query", return_value=Answer("a", [])), \
         patch("src.api.routes.chat.answer_query_events", side_effect=lambda *a, **k: iter([Done(Answer("a", []))])):
        json_route = _hammer(client, "POST", f"/api/chat/threads/{thread_id}/messages", 8, headers, body)
        stream_route = _hammer(client, "POST", f"/api/chat/threads/{thread_id}/messages/stream", 8, headers, body)
    assert all(r.status_code == 201 for r in json_route)
    assert [r.status_code for r in stream_route[:7]] == [200] * 7
    assert stream_route[7].status_code == 429 and "Retry-After" in stream_route[7].headers
```

Import `Done` from `src.services.generation` there.

- [ ] **Step 2: Run them and confirm they fail**

Run: `uv run pytest tests/test_chat_stream.py -q`
Expected: FAIL. The stream route answers 404.

- [ ] **Step 3: Implement** (in `src/api/routes/chat.py`)

```python
# One budget of sends per user, whichever route they use (ADR 0027).
_send_limit = limiter.shared_limit("15 per minute", scope="chat_send")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _message_json(message: Message) -> dict:
    return MessageResponse.model_validate(message, from_attributes=True).model_dump(mode="json")
```

Replace `@limiter.limit("15 per minute")` on `create_message` with
`@_send_limit`. Then add:

```python
@bp.post("/threads/<thread_id>/messages/stream")
@jwt_required()
@_send_limit
def stream_message(thread_id: str):
    """create_message, as Server-Sent Events (ADR 0027). Every check that can
    fail is made first, so its error is ordinary JSON; the question is then
    committed, so no transaction stays open while the model writes."""
    body = parse_body(MessageCreateRequest)
    db, thread = _get_owned_thread(thread_id)
    user = get_current_user()
    if budget_exhausted(db, user.id):
        raise TokenBudgetExhaustedError(seconds_until_budget_resets())

    history, shown_plans = _context(db, thread)
    question = Message(thread_id=thread.id, role="user", content=body.content)
    db.add(question)
    db.commit()
    question_json = _message_json(question)
    profile = plan_profile(user)
    user_id = user.id

    def events():
        reset_token_usage()
        recorded = False
        try:
            yield _sse("user_message", {"message": question_json})
            for event in answer_query_events(body.content, history, profile=profile, shown_plans=shown_plans):
                if isinstance(event, Stage):
                    yield _sse("stage", {"stage": event.name})
                elif isinstance(event, Notice):
                    yield _sse("notice", {"text": event.text})
                elif isinstance(event, Delta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, Reset):
                    yield _sse("reset", {})
                elif isinstance(event, Done):
                    record_tokens(db, user_id, token_usage())
                    recorded = True
                    saved = _save_answer(db, thread, body.content, event.answer)
                    db.commit()
                    thread_json = ThreadResponse.model_validate(thread, from_attributes=True).model_dump(mode="json")
                    yield _sse("done", {"message": _message_json(saved), "thread": thread_json})
        except openai.OpenAIError:
            logger.exception("generation failed for thread %s", thread.id)
            record_tokens(db, user_id, token_usage())
            recorded = True
            db.commit()
            yield _sse("error", {"error": "generation failed"})
        finally:
            # Also runs when the client disconnects (GeneratorExit): the spend is real.
            if not recorded:
                record_tokens(db, user_id, token_usage())
                db.commit()

    return Response(stream_with_context(events()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

Import `json`, `Response` and `stream_with_context` from flask,
`answer_query_events`, `Stage`, `Notice`, `Delta`, `Reset` and `Done`. If a
test shows `thread` detached after `db.commit()` when `done` is built, keep the
session's default `expire_on_commit`: attribute access reloads it inside the
context that `stream_with_context` keeps.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/test_chat_stream.py tests/test_chat.py tests/test_rate_limits.py tests/test_token_budget.py -q`
Expected: all PASS.

- [ ] **Step 5: CHANGELOG and commit**

`- \`POST /api/chat/threads/<id>/messages/stream\` streams an answer as Server-Sent Events (user_message, stage, notice, delta, reset, done, error). It shares one 15-per-minute limit with the JSON route.`

```bash
git add src/api/routes/chat.py tests/test_chat_stream.py tests/test_rate_limits.py CHANGELOG.md
git commit -m "Stream answers as Server-Sent Events"
```

### Task A7: ADR 0027, the README, a full check, and the PR

**Files:**
- Create: `docs/decisions/0027-streaming-answers-and-cited-passages.md`
- Modify: `README.md`: the chat API section and the endpoint list.
- Modify: `docs/decisions/0007-*.md` and `docs/decisions/0022-*.md`: one "Amended by ADR 0027" line each, under Status.
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Write ADR 0027**

Use ADR 0026's shape: Status, Context, Decision, Consequences. The content
comes from spec sections 3.1–3.4:

- **Status:** Accepted. Amends ADR 0007 (citations carry a content hash) and
  ADR 0022 (a stream holds one gthread thread).
- **Context:**
  - Answers arrive after 5–40 s.
  - Sources couldn't be read.
  - Threads couldn't be renamed.
- **Decision:**
  - SSE over `fetch`, since `EventSource` can't POST with a Bearer header.
  - The event protocol table.
  - Text is streamed only once grounded, with `reset`.
  - The commit comes before the stream.
  - Spend is recorded in `finally`.
  - The shared send limit.
  - The passage endpoint: addressed by citation id, never chunk id. Brief quotes
    of ≤300 characters (ADR 0013), the Wikipedia licence from the registry, the
    hash statuses, and `https` URLs only.
  - Renaming leaves `updated_at` alone.
- **Consequences:**
  - The JSON route stays.
  - Gunicorn threads bound concurrent streams (8).
  - The Azure ingress timeout (~240 s) exceeds the worst case.
  - An aborted stream saves no answer.
  - Older citations are "unverified".
  - Sub-project 3's ADR becomes 0028.

- [ ] **Step 2: Update the README**

- List the three new endpoints with their limits.
- Add one short paragraph on streaming.
- Link ADR 0027.

- [ ] **Step 3: Run the full check**

Run: `make check`
Expected: ruff clean, pytest green with coverage ≥85%, bandit and pip-audit
clean, and `alembic check` clean. Fix anything that fails before continuing.

- [ ] **Step 4: Commit and push**

```bash
git add docs/decisions README.md CHANGELOG.md
git commit -m "Record ADR 0027: streaming answers, cited passages, and renaming threads"
git push -u origin feature_chat_redesign_api
```

- [ ] **Step 5: Open the PR, marked ready for review**

`gh pr create --base main --title "Chat backend: streaming answers, cited passages, renaming threads"`.
The body covers the problem, the implementation, validation evidence (the
`make check` summary, the new test counts), and the security, DB and API
impact: the migration, the three endpoints, the shared limit and ADR 0027. No
AI attribution. Wait for green CI, and report the PR URL.

---

# Part B — Frontend (`feature_chat_redesign_ui`)

Run everything from `frontend/`. Read `frontend/CLAUDE.md`. The existing
patterns: `vi.mock("../../services/chatService")`, `useAuth` mocked in hook
tests, and `renderHook` for hooks. Visual markup, class names and copy come
from `docs/design/chat-redesign/*.dc.html` (see its README). The backend
contracts are spec section 3. Part A is built in parallel, so every network
call in Part B's tests is mocked.

### Task B1: Dependencies, tokens and theme

**Files:**
- Modify: `package.json` and `package-lock.json`
- Modify: `src/index.css`: the tokens, and the theme selectors.
- Modify: every CSS file, to use the renamed tokens.
- Create: `src/hooks/useTheme.js` and `src/hooks/useTheme.test.js`
- Modify: `src/main.jsx`: `applyTheme(readTheme())` before render, and `MotionConfig`.
- Modify: `index.html`: add the Plex weights the design uses (Sans 400/500/600, Serif 500/600, already present).
- Replace: `public/favicon.svg` (Vite's logo) with the brass seal mark: a circle
  `#96651F` holding a Plex Serif-style "P" in `#FFF8EA`, as an SVG path or
  text.

**Interfaces:**
- Produces:
  - `readTheme(): "system" | "light" | "dark"`.
  - `applyTheme(theme): void`, which sets or removes `document.documentElement.dataset.theme`.
  - `useTheme(): { theme, setTheme }`.
  - The CSS tokens `--paper --sheet --sheet-2 --ink --ink-soft --rule --rule-strong --seal --seal-deep --seal-wash --pine --pine-wash --danger --danger-wash --silver --float --serif --sans`.

- [ ] **Step 1: Install the dependencies, pinned**

```bash
npm install --save-exact lucide-react motion react-markdown remark-gfm
npm audit --omit=dev
```

Expected: they are added to `dependencies` without `^`, and the audit finds 0
vulnerabilities. Record the installed versions in the commit message body.

- [ ] **Step 2: Write the failing test** (`src/hooks/useTheme.test.js`)

```js
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { applyTheme, readTheme, useTheme } from "./useTheme";

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("theme", () => {
  it("defaults to system", () => {
    expect(readTheme()).toBe("system");
  });

  it("ignores a stored value it doesn't know", () => {
    localStorage.setItem("policypal.theme", "sepia");
    expect(readTheme()).toBe("system");
  });

  it("stores and applies a choice, and system clears it", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setTheme("dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("policypal.theme")).toBe("dark");
    act(() => result.current.setTheme("system"));
    expect(document.documentElement.dataset.theme).toBeUndefined();
    expect(localStorage.getItem("policypal.theme")).toBeNull();
    expect(result.current.theme).toBe("system");
  });

  it("applyTheme sets the attribute", () => {
    applyTheme("light");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
```

- [ ] **Step 3: Run it and confirm it fails.** Run `npx vitest run src/hooks/useTheme.test.js`. Expected: FAIL, because the module isn't found.

- [ ] **Step 4: Implement `src/hooks/useTheme.js`**

```js
import { useCallback, useState } from "react";

const KEY = "policypal.theme";
const CHOICES = ["system", "light", "dark"];

// localStorage, unlike the session: a theme is a device preference, not a secret.
export function readTheme() {
  try {
    const stored = localStorage.getItem(KEY);
    return CHOICES.includes(stored) ? stored : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
}

export function useTheme() {
  const [theme, setThemeState] = useState(readTheme);

  const setTheme = useCallback((next) => {
    try {
      if (next === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      // Storage unavailable: the choice holds for this page only.
    }
    applyTheme(next);
    setThemeState(next);
  }, []);

  return { theme, setTheme };
}
```

- [ ] **Step 5: Rewrite the tokens in `src/index.css`**

- **Light palette.** Copy the `.pp` block's light values from
  `docs/design/chat-redesign/tokens.css` onto bare `:root`, as the custom
  properties listed under Produces.
- **Dark palette.** Copy the `.pp.dark` values into both
  `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … color-scheme: dark; } }`
  and `:root[data-theme="dark"] { … color-scheme: dark; }`.
- **Radii.** Keep `--radius` as `10px`, and add `--radius-lg: 16px`.
- **Base styles.** `body` gets `background: var(--paper)`, `font-family:
  var(--sans)`, a font size of 15px, a line height of 1.55, and
  `font-variant-numeric` left to components. Headings use `var(--serif)` at
  weight 500.
- **Keep** `.visually-hidden`, the focus ring (`outline: 2px solid var(--seal)`)
  and the reduced-motion block.
- **Rename across every CSS file:**

  | Old token | New token |
  | --- | --- |
  | `--surface` | `--sheet` |
  | `--ink-muted` | `--ink-soft` |
  | `--seal-strong` | `--seal-deep` |
  | `--danger-surface` | `--danger-wash` |
  | `--font-display` | `--serif` |
  | `--font-body` | `--sans` |

  Check with `grep -rn "\-\-surface\|ink-muted\|seal-strong\|danger-surface\|font-display\|font-body" src`,
  which should find nothing.

In `src/main.jsx`, call `applyTheme(readTheme())` before `createRoot`, and wrap
`<App />` in `<MotionConfig reducedMotion="user">` from `motion/react`.

- [ ] **Step 6: Run everything.** Run `npm test && npm run lint && npm run build`. Expected: all green.

- [ ] **Step 7: CHANGELOG and commit**

```bash
git add package.json package-lock.json index.html public/favicon.svg src ../CHANGELOG.md
git commit -m "Adopt the redesign's tokens and a remembered light, dark or system theme"
```

### Task B2: The streaming client and the new chat services

**Files:**
- Create: `src/services/sse.js` and `src/services/sse.test.js`
- Modify: `src/services/apiClient.js`: extract `errorFor`, and add `apiStream`.
- Modify: `src/services/apiClient.test.js`
- Modify: `src/services/chatService.js`: add `streamMessage`, `renameThread` and `getSource`.

**Interfaces:**
- Produces:
  - `createSseParser(onEvent: ({event, data}) => void): { push(text), end() }`.
  - `apiStream(path, { token, body, signal, onEvent }): Promise<void>`.
    It rejects with an `ApiError` or `SessionExpiredError` before the stream,
    as `apiFetch` does, and rethrows `AbortError`.
  - `chatService.streamMessage(token, threadId, content, { signal, onEvent })`.
  - `chatService.renameThread(token, threadId, title) → ThreadResponse`.
  - `chatService.getSource(token, sourceId) → PassageResponse`.

- [ ] **Step 1: Write the failing tests** (`src/services/sse.test.js`)

```js
import { describe, expect, it, vi } from "vitest";
import { createSseParser } from "./sse";

describe("createSseParser", () => {
  it("parses events split across chunks", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);
    parser.push('event: delta\ndata: {"te');
    parser.push('xt":"Hi"}\n\nevent: stage\ndata: {"stage":"writing"}\n\n');
    expect(onEvent.mock.calls.map(([e]) => e)).toEqual([
      { event: "delta", data: { text: "Hi" } },
      { event: "stage", data: { stage: "writing" } },
    ]);
  });

  it("dispatches a final event with no blank line on end()", () => {
    const onEvent = vi.fn();
    const parser = createSseParser(onEvent);
    parser.push('event: done\ndata: {"ok":true}');
    expect(onEvent).not.toHaveBeenCalled();
    parser.end();
    expect(onEvent).toHaveBeenCalledWith({ event: "done", data: { ok: true } });
  });

  it("accepts CRLF line endings", () => {
    const onEvent = vi.fn();
    createSseParser(onEvent).push('event: reset\r\ndata: {}\r\n\r\n');
    expect(onEvent).toHaveBeenCalledWith({ event: "reset", data: {} });
  });
});
```

In `apiClient.test.js`, add tests for `apiStream`. Mock `global.fetch` to
return `{ ok: true, status: 200, body: new ReadableStream({ start(c) {
c.enqueue(new TextEncoder().encode('event: delta\ndata: {"text":"a"}\n\n'));
c.close(); } }) }`. Then check:

- `onEvent` receives the delta.
- A 429 `{error: "daily token budget exhausted"}` rejects with the budget
  message.
- A 401 with a token rejects with `SessionExpiredError`.
- A fetch rejecting with `DOMException("aborted", "AbortError")` is rethrown
  with `name === "AbortError"`.

- [ ] **Step 2: Run them and confirm they fail.** Run `npx vitest run src/services`. Expected: FAIL.

- [ ] **Step 3: Implement**

`src/services/sse.js`:

```js
// A text/event-stream body, split into events. Every event PolicyPal sends
// has one JSON data line (ADR 0027).
export function createSseParser(onEvent) {
  let buffer = "";

  function dispatch(block) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
    }
    if (data.length > 0) onEvent({ event, data: JSON.parse(data.join("\n")) });
  }

  return {
    push(text) {
      buffer += text.replaceAll("\r\n", "\n");
      let end;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        dispatch(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
      }
    },
    end() {
      if (buffer.trim()) dispatch(buffer);
      buffer = "";
    },
  };
}
```

In `apiClient.js`, move the non-ok branch of `apiFetch` into `function
errorFor(response, data, token)`, which **returns** the error. `apiFetch` then
does `throw errorFor(response, data, token)`. Put the unreachable message in a
constant. Then add:

```js
export async function apiStream(path, { token, body, signal, onEvent }) {
  const headers = { "Content-Type": "application/json", Accept: "text/event-stream" };
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method: "POST", headers, body: JSON.stringify(body), signal });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(UNREACHABLE, 0);
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw errorFor(response, data, token);
  }

  // EventSource can't POST or send a Bearer header, so the body is read by hand.
  const parser = createSseParser(onEvent);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
  parser.end();
}
```

`chatService.js`:

```js
export function streamMessage(token, threadId, content, { signal, onEvent }) {
  return apiStream(`/api/chat/threads/${threadId}/messages/stream`, { token, body: { content }, signal, onEvent });
}

export function renameThread(token, threadId, title) {
  return apiFetch(`/api/chat/threads/${threadId}`, { method: "PATCH", token, body: { title } });
}

export function getSource(token, sourceId) {
  return apiFetch(`/api/chat/sources/${sourceId}`, { token });
}
```

- [ ] **Step 4: Run them and confirm they pass.** Run `npx vitest run src/services`. Expected: PASS.

- [ ] **Step 5: CHANGELOG and commit.** Stage `git add src/services ../CHANGELOG.md`, then run `git commit -m "Read streamed answers, rename threads, and fetch cited passages"`.

### Task B3: Pure helpers: markers, thread groups and exchanges

**Files:**
- Create: `src/utils/markers.js` and `src/utils/markers.test.js`
- Create: `src/utils/threadGroups.js` and `src/utils/threadGroups.test.js`
- Create: `src/utils/exchanges.js` and `src/utils/exchanges.test.js`

**Interfaces:**
- Produces:
  - `remarkMarkers({ sources, plans })`: a remark plugin. It emits mdast nodes
    that react-markdown renders as the custom elements `pp-seal`, with props
    `number` and `label`, and `pp-plan`, with props `position` and `planId`
    and the plan's name as children.
  - `copyText(content, sources, plans) → string`.
  - `sourceNumbers(sources) → Map<label, number>`.
  - `groupThreads(threads, now = new Date()) → [{ label: "Today" | "Previous 7 days" | "Earlier", threads }]`.
    Only non-empty groups are returned, in that order, keeping the input order
    within each.
  - `toExchanges(messages) → [{ key, question: Message | null, answer: Message | null }]`.

- [ ] **Step 1: Write the failing tests**

`markers.test.js`:

```js
import { describe, expect, it } from "vitest";
import { copyText, remarkMarkers, sourceNumbers } from "./markers";

const sources = [
  { id: "s1", source: "Sharp - Summary of Benefits - Urgent.pdf" },
  { id: "s2", source: "wiki_Health.txt" },
];
const plans = [{ hios_plan_id: "92499CA0020006", name: "Sharp Silver 70 Premier HMO" }];

function run(text) {
  const tree = { type: "root", children: [{ type: "paragraph", children: [{ type: "text", value: text }] }] };
  remarkMarkers({ sources, plans })(tree);
  return tree.children[0].children;
}

describe("remarkMarkers", () => {
  it("turns a source marker into a numbered seal", () => {
    const [before, seal] = run("Fifty dollars.[Source: wiki_Health.txt]");
    expect(before).toEqual({ type: "text", value: "Fifty dollars." });
    expect(seal.data).toMatchObject({ hName: "pp-seal", hProperties: { number: 2, label: "wiki_Health.txt" } });
  });

  it("splits several labels in one bracket and drops unknown ones", () => {
    const nodes = run("x [Source: Sharp - Summary of Benefits - Urgent.pdf; nope.txt; wiki_Health.txt]");
    expect(nodes.filter((n) => n.data?.hName === "pp-seal").map((n) => n.data.hProperties.number)).toEqual([1, 2]);
  });

  it("turns a known plan marker into a plan ref and leaves an unknown one as text", () => {
    const nodes = run("See [Plan: 92499CA0020006] and [Plan: 11111XX1111111].");
    const ref = nodes.find((n) => n.data?.hName === "pp-plan");
    expect(ref.data.hProperties).toEqual({ position: 1, planId: "92499CA0020006" });
    expect(ref.data.hChildren).toEqual([{ type: "text", value: "Sharp Silver 70 Premier HMO" }]);
    expect(nodes.at(-1).value).toContain("[Plan: 11111XX1111111]");
  });
});

describe("copyText", () => {
  it("writes seals as [n] and plans as names", () => {
    expect(copyText("A [Source: wiki_Health.txt] B [Plan: 92499CA0020006].", sources, plans)).toBe(
      "A [2] B Sharp Silver 70 Premier HMO.",
    );
  });
});

describe("sourceNumbers", () => {
  it("numbers each label by its first position", () => {
    expect([...sourceNumbers([...sources, sources[0]])]).toEqual([
      ["Sharp - Summary of Benefits - Urgent.pdf", 1],
      ["wiki_Health.txt", 2],
    ]);
  });
});
```

`threadGroups.test.js` uses a fixed `now = new Date(2026, 8, 26, 15, 0)`.
Threads updated at 2026-09-26 00:01 go under "Today", 2026-09-25 23:59 under
"Previous 7 days", 2026-09-19 00:00 under "Previous 7 days", and 2026-09-18
23:59 under "Earlier". Empty groups are omitted, and the order within a group
is preserved.

`exchanges.test.js`:

- `[user, assistant, user]` gives two exchanges, the second with `answer: null`.
- An assistant with no question before it gives `{question: null, answer}`.
- Each `key` is the question's id, or else the answer's id.

- [ ] **Step 2: Run them and confirm they fail.** Run `npx vitest run src/utils`. Expected: FAIL.

- [ ] **Step 3: Implement**

`src/utils/markers.js`:

```js
// The model cites as [Source: label; label] and names plans as [Plan: id]
// (src/services/generation.py). These become seals and plan links; nothing
// else in the text is interpreted, and nothing becomes raw HTML.
const MARKER = /\[(Source|Plan):\s*([^\]]+)\]/g;

export function sourceNumbers(sources = []) {
  const numbers = new Map();
  sources.forEach((s, i) => {
    if (!numbers.has(s.source)) numbers.set(s.source, i + 1);
  });
  return numbers;
}

function planIndex(plans = []) {
  return new Map(plans.map((p, i) => [p.hios_plan_id, { position: i + 1, name: p.name }]));
}

function splitText(value, numbers, planned) {
  const nodes = [];
  let last = 0;
  for (const match of value.matchAll(MARKER)) {
    const [whole, kind, body] = match;
    const replacement = [];
    if (kind === "Source") {
      for (const label of body.split(";").map((l) => l.trim()).filter(Boolean)) {
        const number = numbers.get(label);
        if (number) replacement.push({ type: "ppSeal", data: { hName: "pp-seal", hProperties: { number, label }, hChildren: [{ type: "text", value: String(number) }] } });
      }
    } else {
      const plan = planned.get(body.trim());
      if (plan) replacement.push({ type: "ppPlan", data: { hName: "pp-plan", hProperties: { position: plan.position, planId: body.trim() }, hChildren: [{ type: "text", value: plan.name }] } });
    }
    if (kind === "Plan" && replacement.length === 0) continue; // unknown plan: leave the text
    if (match.index > last) nodes.push({ type: "text", value: value.slice(last, match.index) });
    nodes.push(...replacement);
    last = match.index + whole.length;
  }
  if (last < value.length) nodes.push({ type: "text", value: value.slice(last) });
  return nodes;
}

export function remarkMarkers({ sources, plans } = {}) {
  const numbers = sourceNumbers(sources);
  const planned = planIndex(plans);
  function walk(node) {
    if (!Array.isArray(node.children)) return;
    node.children = node.children.flatMap((child) => {
      if (child.type === "text") return splitText(child.value, numbers, planned);
      walk(child);
      return [child];
    });
  }
  return (tree) => walk(tree);
}

export function copyText(content, sources, plans) {
  const numbers = sourceNumbers(sources);
  const planned = planIndex(plans);
  return content.replace(MARKER, (whole, kind, body) => {
    if (kind === "Plan") return planned.get(body.trim())?.name ?? whole;
    return body.split(";").map((l) => numbers.get(l.trim())).filter(Boolean).map((n) => `[${n}]`).join("");
  });
}
```

In the plugin test, `run()` calls `remarkMarkers(...)` and applies the
returned transformer. With react-markdown, pass
`remarkPlugins={[remarkGfm, [remarkMarkers, { sources, plans }]]}`: remark
calls the plugin with the options as its argument, and it returns the
transformer. The signature above satisfies both.

`src/utils/threadGroups.js`:

```js
const DAY = 24 * 60 * 60 * 1000;

export function groupThreads(threads, now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const groups = [
    { label: "Today", threads: [] },
    { label: "Previous 7 days", threads: [] },
    { label: "Earlier", threads: [] },
  ];
  for (const thread of threads) {
    const at = new Date(thread.updated_at).getTime();
    const group = at >= today ? 0 : at >= today - 7 * DAY ? 1 : 2;
    groups[group].threads.push(thread);
  }
  return groups.filter((g) => g.threads.length > 0);
}
```

`src/utils/exchanges.js`:

```js
// Messages as question-and-answer pairs: the transcript sets each question as
// its answer's heading.
export function toExchanges(messages) {
  const exchanges = [];
  for (const message of messages) {
    const open = exchanges.at(-1);
    if (message.role === "assistant" && open && open.answer === null && open.question) {
      open.answer = message;
    } else if (message.role === "assistant") {
      exchanges.push({ key: message.id, question: null, answer: message });
    } else {
      exchanges.push({ key: message.id, question: message, answer: null });
    }
  }
  return exchanges;
}
```

- [ ] **Step 4: Run them and confirm they pass.** Run `npx vitest run src/utils`. Expected: PASS.

- [ ] **Step 5: Commit.** Run `git add src/utils ../CHANGELOG.md && git commit -m "Turn citation markers into seals and plan links, and group threads by date"`.

### Task B4: Generic components

**Files:**
- Modify: `src/components/Button.jsx` and `.test.jsx`. The variants become `primary`, `ghost` and `danger`, and `busy` shows a spinner with "Working…" for screen readers.
- Create: `src/components/IconButton.jsx` and `.test.jsx`. It is a `<button>` with a required `label`, which becomes its `aria-label`, and a lucide icon as children.
- Create: `src/components/Menu.jsx` and `.test.jsx`.
- Modify: `src/components/TextField.jsx` and `.test.jsx`. `type="password"` gets a show/hide `IconButton` (`Eye` / `EyeOff`).
- Create: `src/components/Toast.jsx` and `.test.jsx`. It uses `role="status"` and dismisses itself after `duration` ms (default 2400).
- Modify: `src/components/components.css`, porting `.btn`, `.iconbtn`, `.menu`, `.field` and `.toast` from `tokens.css`.

**Interfaces:**
- Produces:
  - `<Menu label trigger={(props) => <IconButton {...props} …/>} items={[{ label, icon, onSelect, danger? }]} />`.
    The trigger gets `aria-haspopup="menu"`, `aria-expanded` and `onClick`.
    The items are `role="menuitem"`. Arrow Up and Down move focus, Enter or
    Space selects, and Esc or a click outside closes the menu and returns
    focus to the trigger.
  - `<Toast message onDone duration />`.

- [ ] **Step 1: Write the failing tests.** These are the Menu cases; write the others' tests in the same style.

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import IconButton from "./IconButton";
import Menu from "./Menu";

function renderMenu(onRename = vi.fn(), onDelete = vi.fn()) {
  render(
    <Menu
      label="Options for Deductibles"
      trigger={(props) => <IconButton label="Options for Deductibles" {...props}>…</IconButton>}
      items={[{ label: "Rename", onSelect: onRename }, { label: "Delete", onSelect: onDelete, danger: true }]}
    />,
  );
  return { onRename, onDelete };
}

it("opens, moves with arrows, selects with Enter, and closes", async () => {
  const user = userEvent.setup();
  const { onDelete } = renderMenu();
  const trigger = screen.getByRole("button", { name: "Options for Deductibles" });
  await user.click(trigger);
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("menuitem", { name: "Rename" })).toHaveFocus();
  await user.keyboard("{ArrowDown}{Enter}");
  expect(onDelete).toHaveBeenCalled();
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("closes on Escape without selecting", async () => {
  const user = userEvent.setup();
  const { onRename } = renderMenu();
  await user.click(screen.getByRole("button", { name: "Options for Deductibles" }));
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(onRename).not.toHaveBeenCalled();
});
```

TextField: a password field toggles between `type="password"` and `"text"`,
and the button's name switches between "Show password" and "Hide password".
Toast: it renders the message with `role="status"`, and calls `onDone` after
the duration (use fake timers).

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.** Take markup and classes from the artboards: the
  `.menu` in `Main.dc.html` and `SidebarAccount.dc.html`, and the password
  field in `SignIn.dc.html`. The menu animates in with `motion.div` (opacity,
  plus y 4 → 0, over 120 ms). Render the menu in place (absolutely positioned
  under the trigger), not in a portal.
- [ ] **Step 4: Run `npm test` and `npm run lint`; both must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Add icon buttons, an accessible menu, toasts, and a password toggle"`.

### Task B5: The sidebar: search, groups, rename, delete and account

**Files:**
- Modify: `src/features/chat/useThreads.js` and `.test.js`: add `renameThread(id, title)`, and `touchThread(id, title)` also takes a thread's `updated_at`.
- Create, under `src/features/chat/sidebar/`, each with a colocated test: `Sidebar.jsx`, `ThreadSearch.jsx`, `ThreadListItem.jsx`, `AccountMenu.jsx`, `sidebar.css`.
- Delete: `src/features/chat/Sidebar.jsx`, `src/features/chat/ThreadListItem.jsx` and their tests; they move into `sidebar/`.

**Interfaces:**
- Consumes: `groupThreads` (B3), `Menu`, `IconButton` (B4), `useTheme` (B1),
  and `chatService.renameThread` (B2).
- Produces:
  - `useThreads() → { threads, status, error, createThread, removeThread, renameThread, touchThread, retry }`.
    `renameThread(id, title)` is optimistic: it rolls back and rethrows on
    failure.
  - `<Sidebar threads status selectedThreadId onSelect onCreate onDelete onRename onHide />`.

- [ ] **Step 1: Write the failing tests**
  - **`useThreads.renameThread`:**
    - it updates the title at once and calls the service;
    - on rejection it restores the old title and rethrows.
  - **`ThreadListItem`:**
    - Rename, from the menu, shows an input labelled "Thread name" holding the
      current title;
    - Enter calls `onRename(id, "New")` with the trimmed value;
    - Esc restores the title without calling it;
    - a blank value is refused, with "Enter a name" shown and nothing called;
    - Delete, from the menu, shows "Delete **{title}** and its answers?", and
      "Keep it" cancels;
    - the "Delete" button calls `onDelete(id)`;
    - the active thread has `aria-current="page"`.
  - **`Sidebar`:**
    - it renders the group headings "Today" and "Earlier" from fixed dates
      (`vi.setSystemTime`);
    - typing "mri" in "Search your questions" filters case-insensitively and
      wraps each match in `<mark>`;
    - with no match it says "No questions match";
    - the clear button restores the list;
    - the loading hint is "Loading your questions…", and the empty hint is
      "Your questions will show up here.";
    - "New question" calls `onCreate`;
    - "Hide the sidebar" calls `onHide`.
  - **`AccountMenu`:**
    - it shows the email;
    - the radio group "Theme" has System, Light and Dark, and choosing Dark
      calls `setTheme("dark")` (mock `useTheme`);
    - "Profile" links to `/profile`;
    - "Sign out" calls `logout`;
    - it lists the shortcuts, with the Mac key shown as ⌘ when
      `navigator.platform` includes "Mac", and Ctrl otherwise.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**, porting markup and copy from `Main.dc.html` (the
  aside), `SidebarSearch.dc.html`, `SidebarRename.dc.html` and
  `SidebarAccount.dc.html`.
  - Icons from `lucide-react`: `PanelLeft`, `Plus`, `Search`, `X`,
    `Ellipsis`, `Pencil`, `Trash2`, `ChevronsUpDown`, `User`, `Sun`, `Moon`,
    `LogOut`.
  - `renameThread` in `useThreads`:

  ```js
  async function renameThread(threadId, title) {
    const before = threads.find((t) => t.id === threadId);
    setThreads((prev) => prev.map((t) => (t.id === threadId ? { ...t, title } : t)));
    try {
      const saved = await chatService.renameThread(token, threadId, title);
      setThreads((prev) => prev.map((t) => (t.id === threadId ? saved : t)));
    } catch (err) {
      setThreads((prev) => prev.map((t) => (t.id === threadId ? before : t)));
      if (err instanceof SessionExpiredError) expireSession();
      throw err;
    }
  }
  ```

  The search highlight splits the title on a case-insensitive match of the
  escaped query and wraps the matches in `<mark>`. It never uses
  `dangerouslySetInnerHTML`.
- [ ] **Step 4: Run `npm test` and `npm run lint`; both must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Search, group, rename and delete threads from a redesigned sidebar"`.

### Task B6: useMessages streams, and can stop

**Files:**
- Modify: `src/features/chat/useMessages.js` and `.test.js`

**Interfaces:**
- Consumes: `chatService.streamMessage` (B2).
- Produces: `useMessages(threadId, onThreadUpdated) → { messages, status, error, live, isSending, sendError, stoppedId, finishedId, send, stop, retry }`.
  - `live` is `null`, or `{ questionId, stages: string[], notices: string[], text: string }`.
  - `stoppedId` is the id of the question whose answer was stopped. It is
    cleared on the next send.
  - `finishedId` is the id of the last answer to finish streaming in this
    session. It drives the stamp.
  - `onThreadUpdated(thread)` receives the `thread` from `done`.

- [ ] **Step 1: Write the failing tests.** Keep the existing load and switch
  tests, and add these. `streamMessage.mockImplementation` drives
  `opts.onEvent`.

```js
function streamWith(events) {
  chatService.streamMessage.mockImplementation(async (_t, _id, _c, { onEvent }) => {
    for (const e of events) onEvent(e);
  });
}

it("streams stages, notices and text, then replaces the draft with done", async () => {
  chatService.listMessages.mockResolvedValue([]);
  const onThreadUpdated = vi.fn();
  const saved = { id: "a1", role: "assistant", content: "Notice.\n\nAnswer.", sources: [], plans: [] };
  streamWith([
    { event: "user_message", data: { message: { id: "q1", role: "user", content: "Q" } } },
    { event: "stage", data: { stage: "searching" } },
    { event: "notice", data: { text: "Notice." } },
    { event: "delta", data: { text: "Ans" } },
    { event: "done", data: { message: saved, thread: { id: "t1", title: "Q" } } },
  ]);
  const { result } = renderHook(() => useMessages("t1", onThreadUpdated));
  await waitFor(() => expect(result.current.status).toBe("ready"));
  await act(() => result.current.send("Q"));
  expect(result.current.messages.map((m) => m.id)).toEqual(["q1", "a1"]);
  expect(result.current.live).toBeNull();
  expect(result.current.finishedId).toBe("a1");
  expect(onThreadUpdated).toHaveBeenCalledWith({ id: "t1", title: "Q" });
});

it("reset clears the streamed text", async () => {
  chatService.listMessages.mockResolvedValue([]);
  let emit;
  chatService.streamMessage.mockImplementation((_t, _i, _c, { onEvent }) => new Promise(() => { emit = onEvent; }));
  const { result } = renderHook(() => useMessages("t1", vi.fn()));
  await waitFor(() => expect(result.current.status).toBe("ready"));
  act(() => { result.current.send("Q"); });
  act(() => emit({ event: "delta", data: { text: "Let me look" } }));
  expect(result.current.live.text).toBe("Let me look");
  act(() => emit({ event: "reset", data: {} }));
  expect(result.current.live.text).toBe("");
});

it("a repeated stage moves to the end", async () => {
  // Same setup: emit stage writing, stage plans, stage writing → ["plans", "writing"].
});

it("an error event keeps the saved question and shows the send error", async () => {
  // streamWith([user_message q1, { event: "error", data: { error: "generation failed" } }])
  // → messages ["q1"], sendError "PolicyPal couldn't write an answer just now. Try again.", live null.
});

it("a failure before the stream removes the optimistic question", async () => {
  // streamMessage rejects with new ApiError("You're sending requests too quickly. Wait a moment and try again.", 429)
  // → messages [], sendError is that message.
});

it("stop aborts, keeps the question, and marks it stopped", async () => {
  // streamMessage awaits a promise that rejects with DOMException("aborted", "AbortError") when opts.signal aborts;
  // after user_message q1, act(() => result.current.stop()) → live null, stoppedId "q1", messages ["q1"],
  // and streamMessage's signal.aborted is true.
});

it("an expired session calls expireSession", async () => {
  // streamMessage rejects with new SessionExpiredError() → expireSession called.
});
```

Write the four abbreviated cases in full, following the comment in each.

- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.** Replace `send` and the `isSending` state:

```js
const ANSWER_FAILED = "PolicyPal couldn't write an answer just now. Try again.";

// in the hook:
const [live, setLive] = useState(null);
const [stoppedId, setStoppedId] = useState(null);
const [finishedId, setFinishedId] = useState(null);
const controllerRef = useRef(null);

async function send(content) {
  const optimistic = { id: `temp-${tempIdCounter++}`, role: "user", content, created_at: new Date().toISOString() };
  let questionId = optimistic.id;
  let saved = false;
  const controller = new AbortController();
  controllerRef.current = controller;
  setSendError("");
  setStoppedId(null);
  setMessages((prev) => [...prev, optimistic]);
  setLive({ questionId, stages: [], notices: [], text: "" });

  try {
    await chatService.streamMessage(token, threadId, content, {
      signal: controller.signal,
      onEvent: ({ event, data }) => {
        if (event === "user_message") {
          saved = true;
          questionId = data.message.id;
          setMessages((prev) => prev.map((m) => (m.id === optimistic.id ? data.message : m)));
          setLive((l) => ({ ...l, questionId }));
        } else if (event === "stage") {
          setLive((l) => ({ ...l, stages: [...l.stages.filter((s) => s !== data.stage), data.stage] }));
        } else if (event === "notice") {
          setLive((l) => ({ ...l, notices: [...l.notices, data.text] }));
        } else if (event === "delta") {
          setLive((l) => ({ ...l, text: l.text + data.text }));
        } else if (event === "reset") {
          setLive((l) => ({ ...l, text: "" }));
        } else if (event === "done") {
          setMessages((prev) => [...prev, data.message]);
          setFinishedId(data.message.id);
          onThreadUpdated?.(data.thread);
        } else if (event === "error") {
          throw new ApiError(ANSWER_FAILED, 502);
        }
      },
    });
  } catch (err) {
    if (err?.name === "AbortError") setStoppedId(questionId);
    else if (err instanceof SessionExpiredError) expireSession();
    else {
      if (!saved) setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setSendError(err.message);
    }
  } finally {
    controllerRef.current = null;
    setLive(null);
  }
}

function stop() {
  controllerRef.current?.abort();
}
```

Return `isSending: live !== null`. Also abort any stream in progress when
`threadId` changes: in the existing "switched thread" block, call
`controllerRef.current?.abort()`. Import `ApiError` from `apiClient`.

- [ ] **Step 4: Run the tests and confirm they pass.** Run `npx vitest run src/features/chat/useMessages.test.js`.
- [ ] **Step 5: Commit.** Run `git commit -m "Stream answers into the transcript, and let them be stopped"`.

### Task B7: The transcript: exchanges, Markdown answers, seals, streaming and the empty state

**Files:**
- Create, under `src/features/chat/transcript/`, each with a test:
  `Transcript.jsx`, `Exchange.jsx`, `AnswerBody.jsx`, `Seal.jsx`,
  `PlanRef.jsx`, `AnswerFooter.jsx`, `StreamingAnswer.jsx`, `EmptyState.jsx`,
  `JumpToLatest.jsx`, `transcript.css`.
- Delete, moving them into `transcript/`: `MessageTranscript.jsx`,
  `MessageItem.jsx`, `EmptyState.jsx` and their tests, and
  `components/ThinkingIndicator.*`.

**Interfaces:**
- Consumes: `toExchanges`, `remarkMarkers`, `copyText` (B3); `useMessages`'s
  `live`, `stoppedId` and `finishedId` (B6); `PlanComparison` (restyled in B9).
- Produces:
  - `<Transcript messages status error live stoppedId finishedId onPrompt onRetry onAskAgain onOpenSource onAskAboutPlan />`.
  - `onOpenSource(message, sourceId)` opens the Sources panel on that source.
  - `onAskAboutPlan(position, name)` fills the composer.
  - `onAskAgain(content)` re-sends a stopped question.

- [ ] **Step 1: Write the failing tests.** Cover these:
  - **`AnswerBody`:**
    - It renders `**bold**` as `<strong>` and a GFM table as a `<table>`.
    - The literal `<script>alert(1)</script>` renders as text and no script
      element exists.
    - A `javascript:` link renders with no `href`.
    - An `https` link has `target="_blank"` and `rel="noopener noreferrer"`.
    - `[Source: wiki_Health.txt]` renders a button named "Source 2", and
      clicking it calls `onOpenSource(sourceId)`.
    - `[Plan: id]` renders a button with the plan's number and name, and
      clicking it scrolls to and flashes `#plan-{messageId}-{position}`. Mock
      `scrollIntoView`, and check the row gains then loses `.flash` (fake
      timers, 1400 ms).
  - **`Seal`:** a stamp class is applied only when `stamp` is true.
  - **`Exchange`:**
    - the question renders as an `h2` in the serif class, with its time;
    - the answer's notice paragraphs render as notes;
    - `stamp={exchange.answer.id === finishedId}` is passed down, so reloaded
      history never stamps.
  - **`AnswerFooter`:**
    - a chip per source, "{n} {title}" (the label formatted by
      `formatSourceLabel`), opens that source;
    - Copy calls `navigator.clipboard.writeText` with `copyText(...)` and shows
      "Copied" for 1.6 s;
    - a rejected write shows "Couldn't copy".
  - **`StreamingAnswer`:**
    - the stages `["searching", "plans"]` show "Searching the references" as
      done and "Searching plans near you" as current;
    - a "Writing the answer" step is pending until `writing` arrives;
    - the text renders through `AnswerBody` with the caret;
    - the region has `aria-live="polite"` and `aria-busy="true"`.
  - **`Transcript`:**
    - loading shows "Loading conversation…";
    - an error shows the banner and "Try again";
    - an empty thread shows `EmptyState`;
    - a stopped question shows "You stopped this answer." and "Ask again";
    - `JumpToLatest` appears when scrolled more than 200 px from the bottom
      (set `scrollTop`, `scrollHeight` and `clientHeight` and fire `scroll`),
      and clicking it scrolls to the bottom.
  - **`EmptyState`:**
    - the heading "What would you like to know about your coverage?";
    - four starters, and clicking one calls `onPrompt(text)`.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**, porting from `Main.dc.html`,
  `Streaming.dc.html` and `Empty.dc.html`. The details:

  - **`AnswerBody`:**

    ```jsx
    <ReactMarkdown
      remarkPlugins={[remarkGfm, [remarkMarkers, { sources: message.sources, plans: message.plans }]]}
      urlTransform={(url) => safeUrl(url) ?? ""}
      components={{
        a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}<span className="visually-hidden"> (opens in a new tab)</span></a> : <>{children}</>,
        "pp-seal": ({ number, label }) => <Seal number={Number(number)} stamp={stamp} onClick={() => onOpenSource(sourceIdFor(label))} />,
        "pp-plan": ({ position, planId, children }) => <PlanRef position={Number(position)} messageId={message.id} planId={planId}>{children}</PlanRef>,
        table: ({ children }) => <div className="md-table-scroll" tabIndex={0}><table>{children}</table></div>,
      }}
    >{content}</ReactMarkdown>
    ```

    `sourceIdFor(label)` is the id of the first source in `message.sources`
    whose `source === label`. Never add `rehype-raw`.
  - **`Seal`:** a `<button className="seal">` with `aria-label="Source {n}"`.
    When `stamp` is true, it is wrapped in `motion.span` with
    `initial={{ scale: 1.9, rotate: -14, opacity: 0 }}`,
    `animate={{ scale: 1, rotate: 0, opacity: 1 }}` and
    `transition={{ type: "spring", stiffness: 500, damping: 18, delay: index * 0.08 }}`.
  - **Stage wording:**

    ```js
    const STAGES = {
      understanding: "Understanding your question",
      searching: "Searching the references",
      plans: "Searching plans near you",
      coverage: "Reading Summaries of Benefits",
      writing: "Writing the answer",
    };
    ```

    The steps shown are the stages received, in order, plus "Writing the
    answer" as pending if it hasn't arrived. Every step before the last is
    ticked (`Check`), and the last spins.
- [ ] **Step 4: Run `npm test` and `npm run lint`; both must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Render answers as Markdown with citation seals, plan links and live progress"`.

### Task B8: The Sources panel

**Files:**
- Create, under `src/features/chat/sources/`, each with a test:
  `SourcesPanel.jsx`, `SourceCard.jsx`, `useSource.js`, `sources.css`.

**Interfaces:**
- Consumes: `chatService.getSource` (B2) and `useMediaQuery` (B9; create it
  here if B9 hasn't yet).
- Produces:
  - `useSource(sourceId) → { status: "loading" | "ready" | "error", passage, retry }`.
    It caches per id in a module-level `Map`, and clears the cache on sign-out
    (export `clearSourceCache`).
  - `<SourcesPanel message selectedSourceId onSelect onClose />`. It is a
    right-hand column above 720 px and a bottom sheet with a scrim at or below
    it.

- [ ] **Step 1: Write the failing tests.** Cover these:
  - **`useSource`:**
    - it fetches once per id, and a second hook for the same id reuses the
      cache;
    - an error shows "This source couldn't be loaded." with "Try again".
  - **`SourceCard`**, one test per `status`:
    - `ok`: the quote, the match meter (`aria-label="94% match"`), and the link
      "Carrier's PDF" for `sbc` or "Read on Wikipedia" for `wikipedia`, opening
      in a new tab;
    - `unverified`: the quote plus "This passage may have changed since the
      answer.";
    - `changed` and `missing`: no quote, and "This passage has changed since
      the answer and can't be shown.";
    - Wikipedia: the credit "Text from the Wikipedia article “Health insurance”,
      by its contributors, under CC BY-SA 4.0.", with the licence as a link to
      `license.url`.
  - **`SourcesPanel`:**
    - it lists one card per source, numbered by the same rule as the seals
      (`sourceNumbers`);
    - the selected card has `aria-current="true"` and is scrolled into view;
    - "Close sources" calls `onClose`;
    - at a phone width (mock `useMediaQuery` true) it renders as
      `role="dialog"` named "Sources", Esc closes it, and focus moves into it
      on open.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**, porting the `.panel` and `.src` markup and copy
  from `Main.dc.html`, and the `.sheet` from `Mobile.dc.html`.
  - The panel slides in with `motion.aside` (x 24 → 0, opacity).
  - The sheet slides with `y: "100%"` → 0 inside `AnimatePresence`.
  - The meter's width is `Math.round(source.relevance * 100)`%.
  - The quote shows `|` separators in the muted colour: split on ` | ` and
    join with `<span className="muted"> | </span>`.
- [ ] **Step 4: Run `npm test` and `npm run lint`; both must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Show each citation's passage, source and licence in a Sources panel"`.

### Task B9: Composer, shortcuts, app shell, chat page and plan table

**Files:**
- Create, under `src/features/chat/composer/`, with tests: `Composer.jsx` (it
  replaces `features/chat/Composer.jsx`) and `ProfileNudge.jsx` (moved from
  `features/profile`).
- Create: `src/hooks/useShortcuts.js` and `src/hooks/useMediaQuery.js`, with tests.
- Create: `src/features/chat/AppShell.jsx`, with a test.
- Create: `src/features/chat/ChatHeader.jsx`, with a test.
- Modify: `src/pages/ChatPage.jsx` and its test. Delete `features/chat/ChatWindow.*`, since its logic moves into ChatPage and ChatHeader.
- Modify: `src/features/plans/PlanComparison.jsx`, its test and `plans.css`.
- Modify: `src/features/chat/newThread.integration.test.jsx`, for the streaming send.

**Interfaces:**
- Produces:
  - `useShortcuts({ onNewQuestion, onFocusComposer, onEscape })`.
  - `useMediaQuery(query) → boolean`.
  - `<AppShell sidebar main panel sidebarHidden />`. At ≤720 px the sidebar is
    a drawer with a scrim, opened from the header's menu button.
  - `<Composer ref value onChange onSubmit onStop isSending placeholder />`.
  - `<ChatHeader title onRename sourcesCount sourcesOpen onToggleSources onShowSidebar sidebarHidden />`.
  - `PlanComparison` gains `messageId` and `onAskAboutPlan`.

- [ ] **Step 1: Write the failing tests.** Cover these:
  - **`useShortcuts`:**
    - Ctrl+K and ⌘K call `onNewQuestion` and prevent the default;
    - `/` calls `onFocusComposer`, except while focus is in an input or
      textarea;
    - Escape calls `onEscape`.
  - **`Composer`:**
    - Enter submits the trimmed text, and Shift+Enter does not;
    - an empty or whitespace-only value never submits;
    - while `isSending`, the textarea is disabled, the button is named "Stop
      answering", and clicking it calls `onStop`;
    - the privacy note is present: "Questions and the passages found for them
      are sent to OpenAI to write answers. Don't include personal details.";
    - the hint is "Enter to send, Shift+Enter for a new line".
  - **`ChatHeader`:**
    - clicking the title turns it into an input labelled "Thread name";
    - Enter saves through `onRename`, and Esc cancels;
    - "Sources" shows the count and `aria-pressed`.
  - **`PlanComparison`:**
    - every existing assertion is kept, updated for the new markup;
    - rows show their position numbers 1…n, and each row has
      `id="plan-{messageId}-{n}"`;
    - "Ask about this plan" calls `onAskAboutPlan(n, name)`;
    - the caption is no longer joined with ` · `.
  - **`ChatPage`:**
    - `onAskAboutPlan` fills the composer with `About plan 2, Silver 70 HMO: `
      and focuses it;
    - Ctrl+K creates a thread;
    - Escape while an answer is live calls `stop`;
    - the Sources toggle opens the panel on the latest answer that has
      sources.
  - **`newThread.integration`:**
    - the first message on a new thread is sent through `streamMessage` once
      the thread exists.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement.**
  - **`useShortcuts`:**

    ```js
    import { useEffect } from "react";

    // Ctrl/⌘K new question, "/" to type, Esc to stop or close (spec §4.3).
    export function useShortcuts({ onNewQuestion, onFocusComposer, onEscape }) {
      useEffect(() => {
        function onKeyDown(event) {
          const typing = event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable='true']");
          if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
            event.preventDefault();
            onNewQuestion?.();
          } else if (event.key === "Escape") {
            onEscape?.(event);
          } else if (event.key === "/" && !typing) {
            event.preventDefault();
            onFocusComposer?.();
          }
        }
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
      }, [onNewQuestion, onFocusComposer, onEscape]);
    }
    ```

  - **`useMediaQuery`** uses `window.matchMedia` with a change listener, and
    returns `false` when `matchMedia` is missing (jsdom).
  - **`ChatPage`** owns the draft, `sidebarHidden` (localStorage key
    `policypal.sidebar`, read and written in try/catch), `panel` (`{ messageId,
    sourceId } | null`) and the composer ref. It uses `useMessages`, and
    `useThreads` with `onThreadUpdated={(t) => touchThread(t.id, t.title,
    t.updated_at)}`. It keeps `ChatWindow`'s existing `pendingFirstMessage`
    logic for a new thread. Escape does, in order:
    1. `stop()` if an answer is live;
    2. otherwise it closes the panel;
    3. otherwise it closes the mobile drawer.
  - **The markup** comes from `Main.dc.html` (topbar, dock, composer, jump) and
    `Mobile.dc.html` (nudge, compact topbar).
  - **`PlanComparison`** follows `Main.dc.html`'s `.plans` table:
    - the head reads "{year} {Metal} plans", then "{County} County, {ST}", then
      "Shown {date}", as separate spans;
    - the `premiumNote`, `unreadableNote`, exchange links and SBC notes keep
      their current logic and tests.
- [ ] **Step 4: Run `npm test`, `npm run lint` and `npm run build`; all must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Compose the redesigned chat: shell, header, composer, shortcuts and numbered plan table"`.

### Task B10: Sign-in, register and profile

**Files:**
- Modify: `src/pages/AuthPage.jsx`, `src/features/auth/AuthForm.jsx`, `auth.css` and their tests.
- Create: `src/features/auth/ExampleAnswer.jsx` and its test.
- Modify: `src/pages/ProfilePage.jsx`, `src/features/profile/ProfileForm.jsx`, `ProfileFields.jsx`, `profile.css` and their tests.

**Interfaces:**
- Consumes: `AppShell` and `Sidebar` (B5, B9), `TextField` with its password
  toggle (B4), `Seal` (B7), and `useThreads`.

- [ ] **Step 1: Write the failing tests.** Cover these:
  - **`AuthPage`:**
    - the heading "Answers about your health coverage, with the source for
      every claim.";
    - `ExampleAnswer` shows the two glossary quotes, exactly "A fixed amount
      you pay for a plan-covered service, like $30." and "A percentage of the
      cost that you pay for each plan-covered service, like 20%.";
    - the sign-in heading "Sign in", and register's "Create an account";
    - the expired-session notice is still shown;
    - the password toggle works.
  - **`AuthForm`:** every existing validation test stays green.
  - **`ProfilePage`:**
    - it renders inside the shell, with the sidebar's "New question"
      navigating to `/chat`;
    - the fieldset legend "For comparing plans" is in sentence case, not
      uppercase;
    - it shows the aside "Where this goes";
    - Save shows "Saved. Plan questions now use this profile." with a check
      icon.
  - **`ProfileFields`:** all existing tests stay green.
- [ ] **Step 2: Run them and confirm they fail.**
- [ ] **Step 3: Implement**, porting from `SignIn.dc.html` and
  `Profile.dc.html`. On a phone the auth page shows only the form (the example
  column is hidden at ≤900 px). Remove `text-transform: uppercase` from
  `.profile-fields legend`.
- [ ] **Step 4: Run `npm test`, `npm run lint` and `npm run build`; all must pass.**
- [ ] **Step 5: Commit.** Run `git commit -m "Restyle sign-in, register and profile to match the chat"`.

### Task B11: Docs, the full check, and the PR (after Part A merges)

- [ ] **Step 1: Update the README.** Cover the chat features (streaming, seals
  and sources, rename and search, theme, shortcuts) and the four new frontend
  dependencies. Update `frontend/CLAUDE.md`'s structure table if the folders
  changed.
- [ ] **Step 2: Run the full frontend gates.** Run `npm run lint && npm test && npm run build`, and record the counts.
- [ ] **Step 3: Rebase and push.** Rebase onto `main` once PR A has merged,
  resolving `CHANGELOG.md` by keeping both sets of bullets. Then run `git push
  -u origin feature_chat_redesign_ui`.
- [ ] **Step 4: Playwright pass (the controller, against the local stack:
  `make api`, `npm run dev`, a real sign-in).** Cover each of these:
  - a plan question streams, with its stages;
  - a seal opens its source;
  - rename and search work;
  - the dark theme;
  - a 390×844 viewport, with `document.documentElement.scrollWidth ===
    clientWidth` and the sheet;
  - Stop.

  Screenshots go in the PR.
- [ ] **Step 5: Open the PR.** Run `gh pr create --title "Chat redesign: streaming, citation seals, sources panel, sidebar, themes"`.
  The body covers the problem, the implementation, validation evidence (the
  test counts and screenshots), and the security, DB and API impact. It
  consumes Part A's endpoints and makes no backend change. No AI attribution.
