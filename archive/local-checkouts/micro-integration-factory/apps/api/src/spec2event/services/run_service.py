from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from spec2event.models import (
    Deployment,
    EventLog,
    EventPortalSync,
    GeneratedArtifact,
    GenerationRun,
    RunStepLog,
    SourceUpload,
    TestInvocation,
)

TEXT_FILE_EXTENSIONS = {
    ".java",
    ".xml",
    ".yml",
    ".yaml",
    ".md",
    ".json",
    ".properties",
    ".txt",
    ".dockerfile",
    ".sh",
    ".http",
    ".groovy",
    ".dwl",
    ".code-workspace",
    ".example",
}


def iso(dt: datetime) -> str:
    return dt.isoformat()


def create_upload(
    db: Session,
    filename: str,
    content_type: str,
    raw_content: str,
    summary: dict[str, Any],
    source_type: str = "openapi",
) -> SourceUpload:
    upload = SourceUpload(
        filename=filename,
        content_type=content_type,
        raw_content=raw_content,
        summary_json=summary,
        source_type=source_type,
    )
    db.add(upload)
    db.flush()
    return upload


def create_run(db: Session, upload: SourceUpload, deployment_target: str) -> GenerationRun:
    service_name = upload.summary_json.get("serviceName") or "generated-service"
    run = GenerationRun(
        upload_id=upload.id,
        source_type=upload.source_type,
        service_name=service_name,
        status="pending",
        deployment_target=deployment_target,
        last_message="Waiting to start generation",
    )
    db.add(run)
    db.flush()
    return run


def get_run(db: Session, run_id: str) -> GenerationRun:
    run = db.get(GenerationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def get_upload(db: Session, upload_id: str) -> SourceUpload:
    upload = db.get(SourceUpload, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload


def log_step(
    db: Session, run: GenerationRun, step_name: str, status: str, message: str
) -> RunStepLog:
    entry = RunStepLog(run_id=run.id, step_name=step_name, status=status, message=message)
    if status in {"running", "failed", "partial"}:
        run.status = status
    run.last_message = message
    db.add(entry)
    db.flush()
    return entry


def update_run(
    db: Session,
    run: GenerationRun,
    *,
    status: str | None = None,
    service_name: str | None = None,
    workspace_path: str | None = None,
    canonical_model_json: dict[str, Any] | None = None,
    image_tag: str | None = None,
    service_url: str | None = None,
    last_message: str | None = None,
) -> GenerationRun:
    if status is not None:
        run.status = status
    if service_name is not None:
        run.service_name = service_name
    if workspace_path is not None:
        run.workspace_path = workspace_path
    if canonical_model_json is not None:
        run.canonical_model_json = canonical_model_json
    if image_tag is not None:
        run.image_tag = image_tag
    if service_url is not None:
        run.service_url = service_url
    if last_message is not None:
        run.last_message = last_message
    db.flush()
    return run


def _is_text_file(path: Path) -> bool:
    if path.name in {"Dockerfile", ".dockerignore"}:
        return True
    return path.suffix.lower() in TEXT_FILE_EXTENSIONS


def snapshot_workspace(db: Session, run: GenerationRun, workspace_root: Path) -> None:
    latest_revisions = {
        artifact.path: artifact.revision
        for artifact in db.query(GeneratedArtifact).filter(GeneratedArtifact.run_id == run.id).all()
    }
    for file_path in sorted(workspace_root.rglob("*")):
        if not file_path.is_file() or not _is_text_file(file_path):
            continue
        relative_path = file_path.relative_to(workspace_root).as_posix()
        content = file_path.read_text(encoding="utf-8")
        revision = latest_revisions.get(relative_path, 0) + 1
        artifact = GeneratedArtifact(
            run_id=run.id,
            kind=_infer_artifact_kind(relative_path),
            path=relative_path,
            language=_infer_artifact_language(relative_path),
            revision=revision,
            content=content,
            metadata_json={},
        )
        db.add(artifact)
    db.flush()


def latest_artifacts(db: Session, run_id: str) -> list[GeneratedArtifact]:
    grouped: dict[str, GeneratedArtifact] = {}
    query = (
        db.query(GeneratedArtifact)
        .filter(GeneratedArtifact.run_id == run_id)
        .order_by(GeneratedArtifact.path.asc(), GeneratedArtifact.revision.desc())
    )
    for artifact in query:
        grouped.setdefault(artifact.path, artifact)
    return list(grouped.values())


def update_artifact_content(
    db: Session, run: GenerationRun, path: str, content: str
) -> GeneratedArtifact:
    if not run.workspace_path:
        raise HTTPException(status_code=400, detail="Run workspace not generated yet")
    latest = (
        db.query(GeneratedArtifact)
        .filter(GeneratedArtifact.run_id == run.id, GeneratedArtifact.path == path)
        .order_by(GeneratedArtifact.revision.desc())
        .first()
    )
    revision = 1 if latest is None else latest.revision + 1
    artifact = GeneratedArtifact(
        run_id=run.id,
        kind=_infer_artifact_kind(path),
        path=path,
        language=_infer_artifact_language(path),
        revision=revision,
        content=content,
        metadata_json={"edited": True},
    )
    workspace_file = Path(run.workspace_path) / path
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text(content, encoding="utf-8")
    db.add(artifact)
    db.flush()
    return artifact


def record_deployment(
    db: Session,
    run: GenerationRun,
    *,
    target: str,
    status: str,
    image_tag: str | None = None,
    service_url: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> Deployment:
    deployment = Deployment(
        run_id=run.id,
        target=target,
        status=status,
        image_tag=image_tag,
        service_url=service_url,
        metadata_json=metadata_json or {},
    )
    db.add(deployment)
    if image_tag:
        run.image_tag = image_tag
    if service_url:
        run.service_url = service_url
    db.flush()
    return deployment


def record_event_log(
    db: Session,
    run: GenerationRun,
    *,
    correlation_id: str,
    stage: str,
    topic_name: str | None = None,
    payload_json: dict[str, Any] | None = None,
) -> EventLog:
    event = EventLog(
        run_id=run.id,
        correlation_id=correlation_id,
        stage=stage,
        topic_name=topic_name,
        payload_json=payload_json,
    )
    db.add(event)
    db.flush()
    return event


def record_portal_sync(
    db: Session,
    run: GenerationRun,
    *,
    artifact_type: str,
    artifact_name: str,
    status: str,
    external_id: str | None = None,
    manual_action: str | None = None,
    request_payload_json: dict[str, Any] | None = None,
    response_payload_json: dict[str, Any] | None = None,
) -> EventPortalSync:
    sync = EventPortalSync(
        run_id=run.id,
        artifact_type=artifact_type,
        artifact_name=artifact_name,
        status=status,
        external_id=external_id,
        manual_action=manual_action,
        request_payload_json=request_payload_json,
        response_payload_json=response_payload_json,
    )
    db.add(sync)
    db.flush()
    return sync


def record_test_invocation(
    db: Session,
    run: GenerationRun,
    *,
    operation_id: str | None,
    method: str,
    request_path: str,
    correlation_id: str,
    request_payload_json: dict[str, Any] | None,
    response_status: int | None,
    response_payload_json: dict[str, Any] | None,
) -> TestInvocation:
    invocation = TestInvocation(
        run_id=run.id,
        operation_id=operation_id,
        method=method,
        request_path=request_path,
        correlation_id=correlation_id,
        request_payload_json=request_payload_json,
        response_status=response_status,
        response_payload_json=response_payload_json,
    )
    db.add(invocation)
    db.flush()
    return invocation


def serialize_run(
    run: GenerationRun, *, steps: Iterable[RunStepLog] | None = None
) -> dict[str, Any]:
    ordered_steps = sorted(list(steps or run.step_logs), key=lambda item: item.created_at)
    ordered_deployments = sorted(
        list(run.deployment_records), key=lambda item: item.created_at, reverse=True
    )
    latest_deployment = ordered_deployments[0] if ordered_deployments else None
    active_deployment = None
    if latest_deployment is not None:
        active_deployment = {
            "instance_id": latest_deployment.metadata_json.get("instanceId"),
            "private_service_url": latest_deployment.metadata_json.get("privateServiceUrl"),
            "public_ip": latest_deployment.metadata_json.get("publicIp"),
            "expires_at": latest_deployment.metadata_json.get("expiresAt"),
            "target": latest_deployment.target,
            "status": latest_deployment.status,
        }
    return {
        "id": run.id,
        "upload_id": run.upload_id,
        "source_type": run.source_type,
        "service_name": run.service_name,
        "status": run.status,
        "deployment_target": run.deployment_target,
        "image_tag": run.image_tag,
        "service_url": run.service_url,
        "created_at": iso(run.created_at),
        "updated_at": iso(run.updated_at),
        "last_message": run.last_message,
        "canonical_model": run.canonical_model_json,
        "active_deployment": active_deployment,
        "steps": [
            {
                "id": step.id,
                "step_name": step.step_name,
                "status": step.status,
                "message": step.message,
                "created_at": iso(step.created_at),
            }
            for step in ordered_steps
        ],
    }


def serialize_artifact(
    artifact: GeneratedArtifact, *, include_content: bool = False
) -> dict[str, Any]:
    return {
        "id": artifact.id,
        "run_id": artifact.run_id,
        "kind": artifact.kind,
        "path": artifact.path,
        "language": artifact.language,
        "revision": artifact.revision,
        "created_at": iso(artifact.created_at),
        "content": artifact.content if include_content else None,
    }


def serialize_event_log(event: EventLog) -> dict[str, Any]:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "correlation_id": event.correlation_id,
        "stage": event.stage,
        "topic_name": event.topic_name,
        "payload": event.payload_json,
        "created_at": iso(event.created_at),
    }


def serialize_portal_sync(sync: EventPortalSync) -> dict[str, Any]:
    return {
        "id": sync.id,
        "run_id": sync.run_id,
        "artifact_type": sync.artifact_type,
        "artifact_name": sync.artifact_name,
        "external_id": sync.external_id,
        "status": sync.status,
        "manual_action": sync.manual_action,
        "created_at": iso(sync.created_at),
    }


def _infer_artifact_kind(path: str) -> str:
    if path.startswith("helm/") or path.startswith("chart/"):
        return "helm"
    if path.endswith(".java"):
        return "java"
    if path.endswith(".yaml") or path.endswith(".yml"):
        return "config"
    if path.endswith(".md"):
        return "documentation"
    if path.endswith(".json"):
        return "metadata"
    return "text"


def _infer_artifact_language(path: str) -> str | None:
    if path.endswith(".java"):
        return "java"
    if path.endswith(".json"):
        return "json"
    if path.endswith(".md"):
        return "markdown"
    if path.endswith(".yml") or path.endswith(".yaml"):
        return "yaml"
    return None
