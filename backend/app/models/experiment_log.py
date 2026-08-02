"""ExperimentLog model."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.base import UUIDMixin


class ExperimentLog(Base, UUIDMixin):
    """Log entry for an experiment (beyond TensorBoard)."""

    __tablename__ = "experiment_logs"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("experiments.id"), nullable=False, index=True
    )

    level: Mapped[str] = mapped_column(
        String(20), default="info"
    )  # "info", "warning", "error"
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    experiment = relationship("Experiment", back_populates="logs")

    def __repr__(self) -> str:
        return f"<ExperimentLog(level={self.level})>"
