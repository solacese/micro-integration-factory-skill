"""add source_type to uploads and runs

Revision ID: 0002_add_source_type
Revises: 0001_initial
Create Date: 2026-04-13 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_add_source_type"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "openapi_uploads",
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="openapi"),
    )
    op.add_column(
        "generation_runs",
        sa.Column("source_type", sa.String(length=50), nullable=False, server_default="openapi"),
    )


def downgrade() -> None:
    op.drop_column("generation_runs", "source_type")
    op.drop_column("openapi_uploads", "source_type")
