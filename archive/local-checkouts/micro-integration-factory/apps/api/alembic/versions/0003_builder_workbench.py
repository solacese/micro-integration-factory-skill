"""add builder workbench tables

Revision ID: 0003_builder_workbench
Revises: 0002_add_source_type
Create Date: 2026-05-25 14:30:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_builder_workbench"
down_revision = "0002_add_source_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "captured_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("broker_url", sa.Text(), nullable=False),
        sa.Column("topic_filter", sa.String(length=512), nullable=False),
        sa.Column("topic_name", sa.String(length=512), nullable=False),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_captured_events_subscription_id", "captured_events", ["subscription_id"])

    op.create_table(
        "builder_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "captured_event_id",
            sa.String(length=36),
            sa.ForeignKey("captured_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("transform_language", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("intent_summary", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.JSON(), nullable=True),
        sa.Column("preview_json", sa.JSON(), nullable=True),
        sa.Column(
            "generated_run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "builder_session_id",
            sa.String(length=36),
            sa.ForeignKey("builder_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "worker_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "builder_session_id",
            sa.String(length=36),
            sa.ForeignKey("builder_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("project_path", sa.Text(), nullable=True),
        sa.Column("image_tag", sa.String(length=512), nullable=True),
        sa.Column("logs", sa.Text(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_jobs")
    op.drop_table("chat_messages")
    op.drop_table("builder_sessions")
    op.drop_index("ix_captured_events_subscription_id", table_name="captured_events")
    op.drop_table("captured_events")
