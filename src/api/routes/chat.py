import uuid

import openai
from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.deps import TokenBudgetExhaustedError, get_current_user, get_db, parse_body
from src.api.limiter import limiter
from src.core.logging import get_logger
from src.models.chat import Message, MessagePlan, MessageSource, Thread
from src.schemas.chat import (
    MessageCreateRequest,
    MessageResponse,
    ThreadCreateRequest,
    ThreadResponse,
)
from src.services.generation import answer_query, reset_token_usage, token_usage
from src.services.plan_search import PlanResult
from src.services.profile import MIN_SIGNUP_AGE, plan_profile
from src.services.usage import (
    budget_exhausted,
    record_tokens,
    seconds_until_budget_resets,
)

logger = get_logger(__name__)

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


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
    )


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
@limiter.limit("15 per minute")
def create_message(thread_id: str):
    body = parse_body(MessageCreateRequest)
    db, thread = _get_owned_thread(thread_id)
    user = get_current_user()

    if budget_exhausted(db, user.id):
        raise TokenBudgetExhaustedError(seconds_until_budget_resets())

    # Read before adding the new message, so the question isn't its own history.
    prior = db.execute(
        select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in prior]

    user_message = Message(thread_id=thread.id, role="user", content=body.content)
    db.add(user_message)
    db.flush()

    reset_token_usage()
    try:
        result = answer_query(body.content, history, profile=plan_profile(user))
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

    assistant_message = Message(
        thread_id=thread.id,
        role="assistant",
        content=result.text,
        sources=[
            MessageSource(chunk_id=c.chunk_id, source=c.source, relevance=c.score) for c in result.chunks
        ],
        # A snapshot of what the answer showed, in the order shown (ADR 0011).
        plans=[_plan_row(position, plan) for position, plan in enumerate(result.plans)],
    )
    db.add(assistant_message)
    db.flush()

    if thread.title is None:
        thread.title = body.content[:80]

    response = MessageResponse.model_validate(assistant_message, from_attributes=True)
    return jsonify(response.model_dump(mode="json")), 201
