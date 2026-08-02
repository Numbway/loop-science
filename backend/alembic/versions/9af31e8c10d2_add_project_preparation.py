"""Add project preparation, analysis, and encrypted credentials.

Revision ID: 9af31e8c10d2
Revises: 4e8a12f97c31
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9af31e8c10d2"
down_revision: str | None = "4e8a12f97c31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "paper_analysis",
            postgresql.JSON(astext_type=sa.Text()),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "preparation_config",
            postgresql.JSON(astext_type=sa.Text()),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "encrypted_credentials",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "encrypted_credentials")
    op.drop_column("projects", "preparation_config")
    op.drop_column("projects", "paper_analysis")
