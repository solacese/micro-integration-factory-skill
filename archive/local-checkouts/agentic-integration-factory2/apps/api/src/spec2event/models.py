from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from spec2event.db import Base, utcnow


def new_id() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DemoAdmin(Base):
    __tablename__ = "demo_admins"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(128), unique=True, default="local-admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OpenApiUpload(Base):
    __tablename__ = "openapi_uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    raw_content: Mapped[str] = mapped_column(Text)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    runs: Mapped[list[GenerationRun]] = relationship(back_populates="upload")


class GenerationRun(Base, TimestampMixin):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    upload_id: Mapped[str] = mapped_column(ForeignKey("openapi_uploads.id", ondelete="CASCADE"))
    service_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    deployment_target: Mapped[str] = mapped_column(String(50), default="local_docker")
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    service_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_model_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    deployment_approval_status: Mapped[str] = mapped_column(
        String(50), default="not_requested"
    )
    deployment_approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_approval_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deployment_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deployment_approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    upload: Mapped[OpenApiUpload] = relationship(back_populates="runs")
    artifacts: Mapped[list[GeneratedArtifact]] = relationship(back_populates="run")
    deployment_records: Mapped[list[Deployment]] = relationship(back_populates="run")
    event_portal_syncs: Mapped[list[EventPortalSync]] = relationship(back_populates="run")
    event_logs: Mapped[list[EventLog]] = relationship(back_populates="run")
    test_invocations: Mapped[list[TestInvocation]] = relationship(back_populates="run")
    step_logs: Mapped[list[RunStepLog]] = relationship(back_populates="run")


class GeneratedArtifact(Base):
    __tablename__ = "generated_artifacts"
    __table_args__ = (UniqueConstraint("run_id", "path", "revision", name="uq_artifact_revision"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="artifacts")


class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    target: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    image_tag: Mapped[str | None] = mapped_column(String(512), nullable=True)
    service_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[GenerationRun] = relationship(back_populates="deployment_records")


class EventPortalSync(Base):
    __tablename__ = "event_portal_syncs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    artifact_type: Mapped[str] = mapped_column(String(80))
    artifact_name: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    manual_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="event_portal_syncs")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    correlation_id: Mapped[str] = mapped_column(String(255))
    stage: Mapped[str] = mapped_column(String(80))
    topic_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="event_logs")


class TestInvocation(Base):
    __tablename__ = "test_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(16))
    request_path: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(255))
    request_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="test_invocations")


class SettingSecretMetadata(Base):
    __tablename__ = "settings_secrets_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    secret_name: Mapped[str] = mapped_column(String(128), unique=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RunStepLog(Base):
    __tablename__ = "run_step_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"))
    step_name: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="step_logs")
