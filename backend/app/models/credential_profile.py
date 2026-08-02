"""Reusable user-scoped model and SSH credential profiles."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class CredentialProfile(Base, UUIDMixin, TimestampMixin):
    """Encrypted reusable configuration selected by one or more projects."""

    __tablename__ = "credential_profiles"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kind",
            "name",
            name="uq_credential_profiles_user_kind_name",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    public_config: Mapped[dict] = mapped_column(JSON, default=dict)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user = relationship("User", back_populates="credential_profiles")
