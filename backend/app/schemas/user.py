"""User-related Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    """Base user schema."""
    email: str
    name: str


class UserCreate(UserBase):
    """Schema for user registration."""
    password: str


class UserUpdate(BaseModel):
    """Schema for updating user info."""
    name: str | None = None
    email: str | None = None


class UserResponse(UserBase):
    """Schema for user response (no password)."""
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    """Schema for user login."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse