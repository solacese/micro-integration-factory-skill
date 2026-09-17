"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-17 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "demo_admins",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("username", sa.String(length=128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "openapi_uploads",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "generation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "upload_id",
            sa.String(length=36),
            sa.ForeignKey("openapi_uploads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("deployment_target", sa.String(length=50), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=True),
        sa.Column("image_tag", sa.String(length=512), nullable=True),
        sa.Column("service_url", sa.String(length=512), nullable=True),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column("canonical_model_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "generated_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=40), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "path", "revision", name="uq_artifact_revision"),
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("image_tag", sa.String(length=512), nullable=True),
        sa.Column("service_url", sa.String(length=512), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_portal_syncs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("artifact_name", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("manual_action", sa.Text(), nullable=True),
        sa.Column("request_payload_json", sa.JSON(), nullable=True),
        sa.Column("response_payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("topic_name", sa.String(length=512), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "test_invocations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation_id", sa.String(length=255), nullable=True),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("request_path", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("request_payload_json", sa.JSON(), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "settings_secrets_metadata",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("secret_name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("encrypted_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "run_step_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=36),
            sa.ForeignKey("generation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("run_step_logs")
    op.drop_table("settings_secrets_metadata")
    op.drop_table("test_invocations")
    op.drop_table("event_logs")
    op.drop_table("event_portal_syncs")
    op.drop_table("deployments")
    op.drop_table("generated_artifacts")
    op.drop_table("generation_runs")
    op.drop_table("openapi_uploads")
    op.drop_table("demo_admins")
