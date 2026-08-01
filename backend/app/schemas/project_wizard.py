"""Schemas for the end-to-end project creation wizard."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.ai import ProjectConfig


class PaperUploadResponse(BaseModel):
    """Parsed paper details and the newly created draft project."""

    project_id: uuid.UUID
    project_name: str
    paper_title: str
    abstract: str
    authors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class DialogAnswerRequest(BaseModel):
    """One answer in a guided configuration dialog."""

    session_id: str
    answer: str = Field(min_length=1, max_length=2000)


class DialogResponse(BaseModel):
    """Either the next question or a completed project configuration."""

    session_id: str
    complete: bool = False
    question: str | None = None
    options: list[str] = Field(default_factory=list)
    input_type: Literal["single", "multi", "text"] | None = None
    config: ProjectConfig | None = None


class GeneratedFile(BaseModel):
    """One generated source file exposed for review."""

    path: str
    language: str
    content: str


class CodeGenerationResponse(BaseModel):
    """Generated framework and the agent's explanation."""

    project_id: uuid.UUID
    files: list[GeneratedFile]
    summary: str


class SaveCodeRequest(BaseModel):
    """Reviewed files to persist in the project repository."""

    files: list[GeneratedFile] = Field(min_length=1, max_length=50)


class SaveCodeResponse(BaseModel):
    """Commit created after saving reviewed source files."""

    project_id: uuid.UUID
    commit_sha: str
    files_saved: int


class StartExperimentResponse(BaseModel):
    """Initial experiment queued from the completed wizard."""

    project_id: uuid.UUID
    experiment_id: uuid.UUID
    status: Literal["queued"]
