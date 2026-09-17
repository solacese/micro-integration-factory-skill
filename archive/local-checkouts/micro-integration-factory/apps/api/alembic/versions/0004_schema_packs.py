"""add schema packs

Revision ID: 0004_schema_packs
Revises: 0003_builder_workbench
Create Date: 2026-06-01 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_schema_packs"
down_revision = "0003_builder_workbench"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_packs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("schema_format", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=120), nullable=True),
        sa.Column("message_type", sa.String(length=160), nullable=True),
        sa.Column("industry", sa.String(length=160), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_schema_packs_schema_format", "schema_packs", ["schema_format"])


def downgrade() -> None:
    op.drop_index("ix_schema_packs_schema_format", table_name="schema_packs")
    op.drop_table("schema_packs")
