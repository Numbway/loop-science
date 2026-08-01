"""Response schemas for the experiment evidence page."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MetricComparison(BaseModel):
    name: str
    current: float
    parent: float | None = None
    delta: float | None = None
    target: float | None = None


class TrainingLogEntry(BaseModel):
    level: Literal["info", "warning", "error"]
    message: str
    timestamp: datetime


class ReferenceEvidence(BaseModel):
    id: uuid.UUID
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    url: str | None = None
    key_contributions: list[str] = Field(default_factory=list)


class TensorBoardEmbed(BaseModel):
    available: bool
    event_file_count: int
    embed_url: str | None = None


class CodeDiffResponse(BaseModel):
    available: bool
    base_branch: str | None = None
    target_branch: str
    files: list[str] = Field(default_factory=list)
    patch: str = ""
    insertions: int = 0
    deletions: int = 0
    truncated: bool = False
    unavailable_reason: str | None = None


class ExperimentDetailResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    paper_title: str
    node_id: str
    parent_node_id: str | None
    parent_experiment_id: uuid.UUID | None = None
    git_branch: str
    status: Literal["pending", "running", "completed", "failed"]
    summary: str
    improvement_description: str
    metrics: dict[str, float] = Field(default_factory=dict)
    metric_comparisons: list[MetricComparison] = Field(default_factory=list)
    target_metrics: dict[str, float] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str | None = None
    code_changes: dict[str, Any] = Field(default_factory=dict)
    code_diff: CodeDiffResponse
    tensorboard: TensorBoardEmbed
    recent_logs: list[TrainingLogEntry] = Field(default_factory=list)
    references: list[ReferenceEvidence] = Field(default_factory=list)
    duration_seconds: int | None = None
    created_by: Literal["ai", "user"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_available: bool = False
