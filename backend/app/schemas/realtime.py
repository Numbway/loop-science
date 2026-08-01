"""Typed project-level realtime events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RealtimeEventType = Literal[
    "connected",
    "heartbeat",
    "experiment_started",
    "experiment_progress",
    "experiment_completed",
    "experiment_failed",
    "experiment_recovery",
    "diagnosis_ready",
    "new_experiment_created",
]
RealtimeExperimentStatus = Literal["pending", "running", "completed", "failed"]


class ProjectRealtimeEvent(BaseModel):
    """One event delivered to every active viewer of a project."""

    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    type: RealtimeEventType
    project_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    experiment_id: uuid.UUID | None = None
    status: RealtimeExperimentStatus | None = None
    epoch: int | None = None
    total_epochs: int | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    diagnosis: str | None = None
    experiment: dict[str, Any] | None = None
    recovery: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
