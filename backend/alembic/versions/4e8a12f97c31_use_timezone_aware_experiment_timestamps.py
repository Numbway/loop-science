"""Use timezone-aware experiment timestamps.

Revision ID: 4e8a12f97c31
Revises: 09b371db1470
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e8a12f97c31"
down_revision: str | None = "09b371db1470"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "experiments",
        "started_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "experiments",
        "completed_at",
        type_=sa.DateTime(timezone=True),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "experiment_logs",
        "timestamp",
        type_=sa.DateTime(timezone=True),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )


def downgrade() -> None:
    op.alter_column(
        "experiment_logs",
        "timestamp",
        type_=sa.DateTime(timezone=False),
        postgresql_using="timestamp AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "experiments",
        "completed_at",
        type_=sa.DateTime(timezone=False),
        postgresql_using="completed_at AT TIME ZONE 'UTC'",
    )
    op.alter_column(
        "experiments",
        "started_at",
        type_=sa.DateTime(timezone=False),
        postgresql_using="started_at AT TIME ZONE 'UTC'",
    )
