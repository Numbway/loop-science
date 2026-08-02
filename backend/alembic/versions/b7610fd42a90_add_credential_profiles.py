"""Add reusable user credential profiles and project selections.

Revision ID: b7610fd42a90
Revises: 9af31e8c10d2
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7610fd42a90"
down_revision: str | None = "9af31e8c10d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credential_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "public_config",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "kind",
            "name",
            name="uq_credential_profiles_user_kind_name",
        ),
    )
    op.create_index(
        op.f("ix_credential_profiles_user_id"),
        "credential_profiles",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credential_profiles_kind"),
        "credential_profiles",
        ["kind"],
        unique=False,
    )
    op.add_column(
        "projects",
        sa.Column("ai_credential_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("ssh_credential_profile_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_ai_credential_profile_id",
        "projects",
        "credential_profiles",
        ["ai_credential_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projects_ssh_credential_profile_id",
        "projects",
        "credential_profiles",
        ["ssh_credential_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_projects_ai_credential_profile_id"),
        "projects",
        ["ai_credential_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_ssh_credential_profile_id"),
        "projects",
        ["ssh_credential_profile_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_projects_ssh_credential_profile_id"),
        table_name="projects",
    )
    op.drop_index(
        op.f("ix_projects_ai_credential_profile_id"),
        table_name="projects",
    )
    op.drop_constraint(
        "fk_projects_ssh_credential_profile_id",
        "projects",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_projects_ai_credential_profile_id",
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "ssh_credential_profile_id")
    op.drop_column("projects", "ai_credential_profile_id")
    op.drop_index(
        op.f("ix_credential_profiles_kind"),
        table_name="credential_profiles",
    )
    op.drop_index(
        op.f("ix_credential_profiles_user_id"),
        table_name="credential_profiles",
    )
    op.drop_table("credential_profiles")
