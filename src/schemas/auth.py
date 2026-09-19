import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from src.schemas.profile import ProfileFields


class RegisterRequest(ProfileFields):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """Travels in the token response, which the browser keeps in
    sessionStorage — so no profile values, only whether one exists."""

    id: uuid.UUID
    email: str
    created_at: datetime
    profile_complete: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
