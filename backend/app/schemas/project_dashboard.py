"""Schemas for the current user's project and experiment ledger."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProjectDashboardItem(BaseModel):
    """One project summarized with its latest experiment state."""

    id: uuid.UUID
    name: str
    workflow: Literal["paper_reproduction", "existing_assets"]
    status: str
    paper_title: str
    created_at: datetime
    updated_at: datetime
    experiment_count: int
    experiment_status_counts: dict[str, int] = Field(default_factory=dict)
    latest_experiment_id: uuid.UUID | None = None
    latest_experiment_status: str | None = None
    latest_metrics: dict[str, Any] = Field(default_factory=dict)
    data_name: str | None = None
    remote_host: str | None = None
    code_entrypoint: str | None = None


class ProjectDashboardResponse(BaseModel):
    """All projects owned by the authenticated user."""

    projects: list[ProjectDashboardItem] = Field(default_factory=list)
