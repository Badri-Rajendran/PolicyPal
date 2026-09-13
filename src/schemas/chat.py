import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ThreadResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class SourceResponse(BaseModel):
    source: str
    chunk_id: str
    relevance: float


class MessageWithSourcesResponse(BaseModel):
    message: MessageResponse
    sources: list[SourceResponse]
