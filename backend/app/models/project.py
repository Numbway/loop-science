"""Project model."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Project(Base, UUIDMixin, TimestampMixin):
    """A research project: one paper reproduction task."""

    __tablename__ = "projects"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Paper information
    paper_title: Mapped[str] = mapped_column(String(500), nullable=False)
    paper_path: Mapped[str] = mapped_column(String(500), nullable=False)
    paper_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    paper_analysis: Mapped[dict] = mapped_column(JSON, default=dict)

    # Improvement configuration
    improvement_targets: Mapped[list] = mapped_column(JSON, default=list)
    target_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5)

    # Git repository path
    repo_path: Mapped[str] = mapped_column(String(500), default="")

    # Experiment readiness. Credentials are encrypted separately and never
    # serialized by project APIs.
    preparation_config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_credentials: Mapped[str] = mapped_column(Text, default="")
    ai_credential_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("credential_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ssh_credential_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("credential_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Status: created, running, paused, completed
    status: Mapped[str] = mapped_column(String(50), default="created")

    # Relationships
    user = relationship("User", back_populates="projects")
    experiments = relationship("Experiment", back_populates="project", cascade="all, delete-orphan")
    reference_papers = relationship(
        "ReferencePaper", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"
