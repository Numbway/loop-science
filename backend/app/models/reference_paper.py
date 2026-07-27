"""ReferencePaper model."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ReferencePaper(Base, UUIDMixin, TimestampMixin):
    """Reference paper in the project library."""

    __tablename__ = "reference_papers"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id"), nullable=False, index=True
    )

    # Paper metadata
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(nullable=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Local storage
    local_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Metadata
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_contributions: Mapped[list] = mapped_column(JSON, default=list)

    # Source and status
    source: Mapped[str] = mapped_column(
        String(50), default="ai_recommended"
    )  # "ai_recommended", "user_uploaded"
    download_status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # "success", "failed", "pending"
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="reference_papers")

    def __repr__(self) -> str:
        return f"<ReferencePaper(title={self.title[:50]})>"