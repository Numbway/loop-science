"""Schemas for reusable user-level credential profiles."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LlmProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    api_key: str = Field(min_length=10, max_length=500)
    provider: Literal["anthropic", "openai_compatible"] = "anthropic"
    model: str = Field(default="claude-sonnet-4-6", min_length=1, max_length=100)
    base_url: str = Field(
        default="https://api.anthropic.com",
        min_length=8,
        max_length=500,
    )


class CredentialProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: Literal["llm", "ssh"]
    public_config: dict
    verified: bool
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectProfileSelectionRequest(BaseModel):
    ai_profile_id: uuid.UUID | None = None
    ssh_profile_id: uuid.UUID | None = None
