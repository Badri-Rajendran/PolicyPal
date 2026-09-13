import uuid

from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from src.api.deps import get_current_user, get_db, parse_body
from src.api.limiter import limiter
from src.models.chat import Message, Thread
from src.schemas.chat import (
    MessageCreateRequest,
    MessageResponse,
    MessageWithSourcesResponse,
    SourceResponse,
    ThreadCreateRequest,
    ThreadResponse,
)
from src.services.generation import answer_query

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

    stmt = select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
    messages = db.execute(stmt).scalars().all()

    return jsonify([MessageResponse.model_validate(m, from_attributes=True).model_dump(mode="json") for m in messages])


@bp.post("/threads/<thread_id>/messages")
@jwt_required()
@limiter.limit("15 per minute")
def create_message(thread_id: str):
    body = parse_body(MessageCreateRequest)
    db, thread = _get_owned_thread(thread_id)

    user_message = Message(thread_id=thread.id, role="user", content=body.content)
    db.add(user_message)
    db.flush()

    answer_text, chunks = answer_query(body.content)

    assistant_message = Message(thread_id=thread.id, role="assistant", content=answer_text)
    db.add(assistant_message)
    db.flush()

    if thread.title is None:
        thread.title = body.content[:80]

    response = MessageWithSourcesResponse(
        message=MessageResponse.model_validate(assistant_message, from_attributes=True),
        sources=[SourceResponse(source=c.source, chunk_id=c.chunk_id, relevance=c.score) for c in chunks],
    )
    return jsonify(response.model_dump(mode="json")), 201
