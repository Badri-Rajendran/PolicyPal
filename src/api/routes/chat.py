import dataclasses
import json
import uuid

import openai
from flask import Blueprint, Response, abort, jsonify, stream_with_context
from flask_jwt_extended import jwt_required
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from src.api.deps import TokenBudgetExhaustedError, get_current_user, get_db, parse_body
from src.api.limiter import limiter
from src.core.logging import get_logger
from src.models.chat import Message, MessagePlan, MessageSource, Thread
from src.schemas.chat import (
    MessageCreateRequest,
    MessageResponse,
    PassageResponse,
    ThreadCreateRequest,
    ThreadRenameRequest,
    ThreadResponse,
)
from src.services.generation import (
    Answer,
    Delta,
    Done,
    Notice,
    Reset,
    ShownPlan,
    Stage,
    answer_query,
    answer_query_events,
    reset_token_usage,
    token_usage,
)
from src.services.passages import content_hash, passage_for
from src.services.plan_search import PlanResult
from src.services.profile import MIN_SIGNUP_AGE, plan_profile
from src.services.usage import (
    budget_exhausted,
    record_tokens,
    seconds_until_budget_resets,
)

logger = get_logger(__name__)

bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# One budget of sends per user, whichever route they use (ADR 0027).
_send_limit = limiter.shared_limit("15 per minute", scope="chat_send")


def _get_owned_thread(thread_id: str):
    """The current user's thread, or a 404 (not 403) if it doesn't exist or belongs to someone else."""
    db = get_db()
    user = get_current_user()

    try:
        parsed_id = uuid.UUID(thread_id)
    except ValueError:
        abort(404)

    thread = db.get(Thread, parsed_id)
    if thread is None or thread.user_id != user.id:
        abort(404)

    return db, thread


def _plan_row(position: int, plan: PlanResult) -> MessagePlan:
    return MessagePlan(
        position=position,
        hios_plan_id=plan.hios_plan_id,
        plan_year=plan.plan_year,
        name=plan.name,
        issuer=plan.issuer,
        metal_level=plan.metal_level,
        plan_type=plan.plan_type,
        monthly_premium=plan.monthly_premium,
        # A child's age, asked about in a question, prices that search and is
        # then dropped: nothing about someone under 13 is stored (ADR 0012).
        premium_age=plan.premium_age if (plan.premium_age or 0) >= MIN_SIGNUP_AGE else None,
        premium_reference=plan.premium_reference,
        deductible=plan.deductible,
        drug_deductible=plan.drug_deductible,
        out_of_pocket_max=plan.out_of_pocket_max,
        hsa_eligible=plan.hsa_eligible,
        quality_rating=plan.quality_rating,
        county_name=plan.county_name,
        state=plan.state,
        benefits_url=plan.benefits_url,
        sbc_status=plan.sbc_status,
    )


def _shown_plans(db, thread_id) -> tuple[ShownPlan, ...]:
    """The plans of the thread's latest answer that showed any, in the order shown (ADR 0014)."""
    latest = (
        select(MessagePlan.message_id)
        .join(Message, Message.id == MessagePlan.message_id)
        .where(Message.thread_id == thread_id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(MessagePlan).where(MessagePlan.message_id == latest).order_by(MessagePlan.position)
    ).scalars()
    return tuple(
        ShownPlan(position=row.position + 1, plan_id=row.hios_plan_id, name=row.name, issuer=row.issuer,
                  metal_level=row.metal_level, plan_year=row.plan_year)
        for row in rows
    )


def _context(db, thread) -> tuple[list[dict], tuple[ShownPlan, ...]]:
    """The thread's history and last-shown plans, read before the new question is added,
    so the question isn't its own history."""
    prior = db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    ).scalars().all()
    return [{"role": m.role, "content": m.content} for m in prior], _shown_plans(db, thread.id)


def _message_json(message: Message) -> dict:
    return MessageResponse.model_validate(message, from_attributes=True).model_dump(mode="json")


def _sse(event: str, data: dict) -> str:
    """One Server-Sent Event. Names and fields are the server's; only text values come from the model."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _save_answer(db, thread, question: str, result: Answer) -> Message:
    """The assistant message with its citations and plan snapshots (ADR 0007, 0011, 0027),
    and the thread's automatic title."""
    message = Message(
        thread_id=thread.id,
        role="assistant",
        content=result.text,
        # In the order a reload returns them (Message.sources), so a seal keeps
        # its number: the live answer is serialized from this list as built.
        sources=[
            MessageSource(chunk_id=c.chunk_id, source=c.source, relevance=c.score,
                          content_sha256=content_hash(c.content))
            for c in sorted(result.chunks, key=lambda c: (-c.score, c.chunk_id, c.source))
        ],
        # A snapshot of what the answer showed, in the order shown (ADR 0011).
        plans=[_plan_row(position, plan) for position, plan in enumerate(result.plans)],
    )
    db.add(message)
    db.flush()
    if thread.title is None:
        thread.title = question[:80]
    return message


@bp.get("/threads")
@jwt_required()
@limiter.limit("60 per minute")
def list_threads():
    db = get_db()
    user = get_current_user()

    stmt = select(Thread).where(Thread.user_id == user.id).order_by(Thread.updated_at.desc())
    threads = db.execute(stmt).scalars().all()

    return jsonify([ThreadResponse.model_validate(t, from_attributes=True).model_dump(mode="json") for t in threads])


@bp.post("/threads")
@jwt_required()
@limiter.limit("30 per minute")
def create_thread():
    body = parse_body(ThreadCreateRequest)
    db = get_db()
    user = get_current_user()

    thread = Thread(user_id=user.id, title=body.title)
    db.add(thread)
    db.flush()

    return jsonify(ThreadResponse.model_validate(thread, from_attributes=True).model_dump(mode="json")), 201


@bp.delete("/threads/<thread_id>")
@jwt_required()
@limiter.limit("30 per minute")
def delete_thread(thread_id: str):
    db, thread = _get_owned_thread(thread_id)
    db.delete(thread)
    return "", 204


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


@bp.get("/threads/<thread_id>/messages")
@jwt_required()
@limiter.limit("60 per minute")
def list_messages(thread_id: str):
    db, thread = _get_owned_thread(thread_id)

    # Eager-load citations and plans: without this the transcript is two
    # queries per message.
    stmt = (
        select(Message)
        .where(Message.thread_id == thread.id)
        .options(selectinload(Message.sources), selectinload(Message.plans))
        .order_by(Message.created_at)
    )
    messages = db.execute(stmt).scalars().all()

    return jsonify([MessageResponse.model_validate(m, from_attributes=True).model_dump(mode="json") for m in messages])


@bp.post("/threads/<thread_id>/messages")
@jwt_required()
@_send_limit
def create_message(thread_id: str):
    body = parse_body(MessageCreateRequest)
    db, thread = _get_owned_thread(thread_id)
    user = get_current_user()

    if budget_exhausted(db, user.id):
        raise TokenBudgetExhaustedError(seconds_until_budget_resets())

    history, shown_plans = _context(db, thread)

    user_message = Message(thread_id=thread.id, role="user", content=body.content)
    db.add(user_message)
    db.flush()

    reset_token_usage()
    try:
        result = answer_query(body.content, history, profile=plan_profile(user), shown_plans=shown_plans)
    except openai.OpenAIError:
        # Whatever billed before the failure (e.g. a successful rewrite call
        # ahead of a timed-out answer call) is real spend — record it rather
        # than letting the rollback below erase it. The user's own message
        # stays too: db.flush() above already assigned it an id, and nothing
        # here raises, so close_db() commits instead of rolling back.
        record_tokens(db, user.id, token_usage())
        logger.exception("generation failed for thread %s", thread.id)
        return jsonify(error="generation failed"), 502
    record_tokens(db, user.id, token_usage())

    assistant_message = _save_answer(db, thread, body.content, result)
    response = MessageResponse.model_validate(assistant_message, from_attributes=True)
    return jsonify(response.model_dump(mode="json")), 201


@bp.post("/threads/<thread_id>/messages/stream")
@jwt_required()
@_send_limit
def stream_message(thread_id: str):
    """create_message, as Server-Sent Events (ADR 0027).

    Every check that can fail is made first, so its error is an ordinary
    response. The question is then committed, so no transaction stays open
    while the model writes, and the answer is saved and committed before
    `done` is sent: `done` carries exactly what was saved.
    """
    body = parse_body(MessageCreateRequest)
    db, thread = _get_owned_thread(thread_id)
    user = get_current_user()
    if budget_exhausted(db, user.id):
        raise TokenBudgetExhaustedError(seconds_until_budget_resets())

    history, shown_plans = _context(db, thread)
    profile = plan_profile(user)
    thread_uuid, user_id = thread.id, user.id
    question = Message(thread_id=thread.id, role="user", content=body.content)
    db.add(question)
    db.flush()
    question_json = _message_json(question)
    db.commit()

    def events():
        # The view's session was closed by its teardown when it returned; this
        # one is the stream's own, committed and closed by the stream's teardown.
        db = get_db()
        reset_token_usage()
        recorded = False
        source = None

        # Marked recorded only once committed: a rolled-back commit took the
        # spend with it, so it must be recorded again.
        def record_spend():
            nonlocal recorded
            if not recorded:
                record_tokens(db, user_id, token_usage())
                db.commit()
                recorded = True

        try:
            yield _sse("user_message", {"message": question_json})
            source = answer_query_events(body.content, history, profile=profile, shown_plans=shown_plans)
            for event in source:
                if isinstance(event, Stage):
                    yield _sse("stage", {"stage": event.name})
                elif isinstance(event, Notice):
                    yield _sse("notice", {"text": event.text})
                elif isinstance(event, Delta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, Reset):
                    yield _sse("reset", {})
                elif isinstance(event, Done):
                    current = db.get(Thread, thread_uuid)
                    if current is None:
                        raise LookupError("thread deleted while it was being answered")
                    saved = _save_answer(db, current, body.content, event.answer)
                    record_tokens(db, user_id, token_usage())
                    db.commit()
                    recorded = True
                    thread_json = ThreadResponse.model_validate(current, from_attributes=True).model_dump(mode="json")
                    yield _sse("done", {"message": _message_json(saved), "thread": thread_json})
        except openai.OpenAIError:
            logger.exception("generation failed for thread %s", thread_uuid)
            record_spend()
            yield _sse("error", {"error": "generation failed"})
        except Exception:
            # Past this point there is no JSON error to fall back on: say so in
            # the stream, never with the exception's text.
            logger.exception("streaming an answer failed for thread %s", thread_uuid)
            db.rollback()
            record_spend()
            yield _sse("error", {"error": "generation failed"})
        finally:
            # Also on a client that went away (GeneratorExit): stop generating,
            # and record the spend so far, which is real. No answer is saved.
            close = getattr(source, "close", None)
            if close is not None:
                close()
            record_spend()

    return Response(stream_with_context(events()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/sources/<source_id>")
@jwt_required()
@limiter.limit("60 per minute")
def get_source(source_id: str):
    """One of the current user's citations, quoted briefly (ADR 0027).

    Addressed by the citation's own id, never by chunk id: chunk ids are
    guessable. Someone else's citation is a 404, never a 403.
    """
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
