"""Experiment model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Experiment(Base, UUIDMixin, TimestampMixin):
    """Experiment node: each node in the experiment tree."""

    __tablename__ = "experiments"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False, index=True
    )

    # Tree structure
    node_id: Mapped[str] = mapped_column(String(20), nullable=False)  # "1", "2-1", "3-2"
    parent_node_id: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Git branch name: "exp/2-1"
    git_branch: Mapped[str] = mapped_column(String(100), nullable=False)

    # Experiment configuration
    improvement_description: Mapped[str] = mapped_column(Text, default="")
    code_changes: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)

    # Experiment results
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_html_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Status and timing
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # "pending", "running", "completed", "failed"
    created_by: Mapped[str] = mapped_column(String(20), default="ai")  # "ai" or "user"
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="experiments")
    logs = relationship("ExperimentLog", back_populates="experiment", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Experiment(node_id={self.node_id}, status={self.status})>"
