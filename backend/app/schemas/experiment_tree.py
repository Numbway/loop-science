"""Response schemas for the project experiment tree."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExperimentTreeNode(BaseModel):
    """One experiment node with all information needed by the tree card."""

    id: uuid.UUID
    node_id: str
    parent_node_id: str | None
    git_branch: str
    improvement_description: str
    status: Literal["pending", "running", "completed", "failed"]
    metrics: dict[str, float] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str | None = None
    duration_seconds: int | None = None
    created_by: Literal["ai", "user"]
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_available: bool = False


class ProjectTreeResponse(BaseModel):
    """Project header and its complete experiment lineage."""

    project_id: uuid.UUID
    name: str
    paper_title: str
    status: Literal["created", "running", "paused", "completed"]
    target_metrics: dict[str, float] = Field(default_factory=dict)
    max_iterations: int
    nodes: list[ExperimentTreeNode]
    updated_at: datetime


class BranchPlanCreate(BaseModel):
    """Three decisions collected by the lightweight branch dialog."""

    focus: Literal["model", "data", "training", "regularization"]
    approach: str = Field(min_length=8, max_length=600)
    budget: Literal["quick", "balanced", "thorough"]

    @field_validator("approach")
    @classmethod
    def normalize_approach(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 8:
            raise ValueError("approach must contain at least 8 non-space characters")
        return normalized


class CreatedBranch(BaseModel):
    """Git lineage created for the new experiment node."""

    name: str
    head_sha: str
    parent_head_sha: str


class BranchPlanResponse(BaseModel):
    """New pending experiment plus its concrete Git branch."""

    node: ExperimentTreeNode
    branch: CreatedBranch
