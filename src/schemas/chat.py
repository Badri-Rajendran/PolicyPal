import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ThreadCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class ThreadRenameRequest(BaseModel):
    # 1 to 200 characters after trimming (ADR 0027): stripped before the
    # length is checked, and anything but a string is left for `str` to refuse.
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def _trimmed(cls, value):
        return value.strip() if isinstance(value, str) else value


class ThreadResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class SourceResponse(BaseModel):
    # The citation's own id: the passage endpoint is addressed by it (ADR 0027).
    id: uuid.UUID
    source: str
    chunk_id: str
    relevance: float


class PassageLicense(BaseModel):
    name: str
    url: str


class PassageResponse(BaseModel):
    """A cited passage as it can be shown now (ADR 0027). Every field is set by
    server code from stored data, never by the model."""

    id: uuid.UUID
    kind: str                      # sbc | wikipedia | healthcare_gov | other
    title: str
    document: str | None
    section: str | None
    quote: str | None              # null when status is changed or missing
    status: str                    # ok | unverified | changed | missing
    url: str | None                # https, public host, or null
    license: PassageLicense | None


class PlanCardResponse(BaseModel):
    """A plan as the answer showed it. Money serializes as an exact string
    ("620.15"), never a float that cannot hold cents."""

    hios_plan_id: str
    plan_year: int
    name: str
    issuer: str
    metal_level: str
    plan_type: str
    monthly_premium: Decimal | None
    premium_age: int | None
    premium_reference: Decimal | None
    deductible: Decimal | None
    drug_deductible: Decimal | None
    out_of_pocket_max: Decimal | None
    hsa_eligible: bool
    quality_rating: int | None
    county_name: str
    state: str
    benefits_url: str | None
    # Whether its Summary of Benefits could be read here; null on older cards (ADR 0017).
    sbc_status: str | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime
    sources: list[SourceResponse] = []
    plans: list[PlanCardResponse] = []


