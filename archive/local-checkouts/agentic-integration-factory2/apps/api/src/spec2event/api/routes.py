from __future__ import annotations

import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from spec2event.db import SessionLocal, get_db
from spec2event.models import EventLog, EventPortalSync, GeneratedArtifact, GenerationRun
from spec2event.schemas import (
    BuildDeployResponse,
    ConnectorSpecRequest,
    CreateRunRequest,
    DatabaseDiscoveryRequest,
    DeploymentApprovalRequest,
    EventLogResponse,
    RunResponse,
    SettingsUpdateRequest,
    SettingsView,
    TestInvocationRequest,
    TestInvocationResponse,
    UpdateArtifactRequest,
    UploadPreviewResponse,
)
from spec2event.security import require_admin
from spec2event.services.connector_spec_service import summarize_connector_spec
from spec2event.services.database_service import canonicalize_database, discover_database_source
from spec2event.services.openapi_service import load_openapi_document, summarize_openapi
from spec2event.services.pipeline import invoke_test
from spec2event.services.queue_service import enqueue_build, enqueue_deploy, enqueue_generation
from spec2event.services.run_service import (
    approve_deployment,
    create_run,
    create_upload,
    get_run,
    get_upload,
    latest_artifacts,
    log_step,
    serialize_artifact,
    serialize_event_log,
    serialize_portal_sync,
    serialize_run,
    update_artifact_content,
)
from spec2event.services.settings_service import settings_view, update_settings

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
AdminAccess = Annotated[None, Depends(require_admin)]
UploadSpecFile = Annotated[UploadFile, File(...)]
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _dump_run_payload(run: GenerationRun) -> str:
    payload = RunResponse.model_validate(serialize_run(run))
    return json.dumps(payload.model_dump(by_alias=True))


def _dump_event_payload(event: EventLog) -> str:
    payload = EventLogResponse.model_validate(serialize_event_log(event))
    return json.dumps(payload.model_dump(by_alias=True))


@router.post("/uploads", response_model=UploadPreviewResponse)
async def upload_openapi(
    file: UploadSpecFile, db: DbSession, _: AdminAccess
) -> UploadPreviewResponse:
    raw_bytes = await file.read()
    raw_content = raw_bytes.decode("utf-8")
    document = load_openapi_document(raw_content)
    summary = {
        **summarize_openapi(document),
        "sourceMode": "openapi",
        "adapterType": "rest-ingress",
        "runtimeBlueprint": "rest_ingress",
    }
    upload = create_upload(
        db,
        file.filename or "spec.yaml",
        file.content_type or "application/yaml",
        raw_content,
        summary,
    )
    db.commit()
    return UploadPreviewResponse(
        upload_id=upload.id,
        filename=upload.filename,
        service_name=summary["serviceName"],
        summary=summary,
        source_mode=summary["sourceMode"],
        runtime_blueprint=summary["runtimeBlueprint"],
    )


@router.post("/uploads/database/discover", response_model=UploadPreviewResponse)
def discover_database_upload(
    payload: DatabaseDiscoveryRequest, db: DbSession, _: AdminAccess
) -> UploadPreviewResponse:
    discovery = discover_database_source(
        database_url=payload.database_url,
        host=payload.host,
        port=payload.port,
        database_name=payload.database_name,
        username=payload.username,
        password=payload.password,
        schema=payload.schema_name,
        preferred_table=payload.preferred_table,
        sslmode=payload.sslmode,
    )
    canonical_model = canonicalize_database(
        discovery,
        application_domain_name=payload.application_domain_name,
        topic_root=payload.topic_root,
    )
    raw_content = json.dumps(
        {
            "discovery": discovery,
            "applicationDomainName": payload.application_domain_name,
            "topicRoot": payload.topic_root,
        }
    )
    summary = {
        **discovery,
        "title": canonical_model["title"],
        "serviceName": canonical_model["serviceName"],
        "sourceMode": "database",
        "adapterType": canonical_model["adapterType"],
        "runtimeBlueprint": canonical_model["runtimeBlueprint"],
        "operationCount": len(canonical_model["operations"]),
        "topics": canonical_model["topics"],
        "applicationDomainName": payload.application_domain_name,
        "topicRoot": payload.topic_root,
    }
    upload = create_upload(
        db,
        f"{canonical_model['serviceName']}-database-source.json",
        "application/json",
        raw_content,
        summary,
    )
    db.commit()
    return UploadPreviewResponse(
        upload_id=upload.id,
        filename=upload.filename,
        service_name=summary["serviceName"],
        summary=summary,
        source_mode=summary["sourceMode"],
        runtime_blueprint=summary["runtimeBlueprint"],
    )


@router.post("/uploads/connector-spec", response_model=UploadPreviewResponse)
def upload_connector_spec(
    payload: ConnectorSpecRequest, db: DbSession, _: AdminAccess
) -> UploadPreviewResponse:
    spec = payload.model_dump(by_alias=True)
    summary = summarize_connector_spec(spec)
    raw_content = json.dumps(spec, indent=2)
    upload = create_upload(
        db,
        f"{summary['serviceName']}-connector-spec.json",
        "application/json",
        raw_content,
        summary,
    )
    db.commit()
    return UploadPreviewResponse(
        upload_id=upload.id,
        filename=upload.filename,
        service_name=summary["serviceName"],
        summary=summary,
        source_mode=summary["sourceMode"],
        runtime_blueprint=summary["runtimeBlueprint"],
    )


@router.post("/runs", response_model=RunResponse)
def create_generation_run(
    payload: CreateRunRequest, db: DbSession, _: AdminAccess
) -> RunResponse:
    upload = get_upload(db, payload.upload_id)
    run = create_run(db, upload, payload.deployment_target)
    db.commit()
    enqueue_generation(run.id, payload.auto_build, payload.auto_deploy)
    return RunResponse.model_validate(serialize_run(run))


@router.get("/runs", response_model=list[RunResponse])
def list_runs(db: DbSession) -> list[RunResponse]:
    runs = db.query(GenerationRun).order_by(GenerationRun.created_at.desc()).all()
    return [RunResponse.model_validate(serialize_run(run)) for run in runs]


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_generation_run(run_id: str, db: DbSession) -> RunResponse:
    run = get_run(db, run_id)
    return RunResponse.model_validate(serialize_run(run))


@router.get("/runs/{run_id}/stream")
def stream_run(run_id: str, db: DbSession) -> StreamingResponse:
    get_run(db, run_id)

    def event_source():
        last_payload = None
        while True:
            with SessionLocal() as stream_db:
                refreshed = stream_db.get(GenerationRun, run_id)
                if refreshed is None:
                    break
                payload = _dump_run_payload(refreshed)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            time.sleep(1)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/runs/{run_id}/event-stream")
def stream_events(run_id: str, db: DbSession) -> StreamingResponse:
    get_run(db, run_id)

    def event_source():
        last_id = ""
        while True:
            with SessionLocal() as stream_db:
                events = (
                    stream_db.query(EventLog)
                    .filter(EventLog.run_id == run_id)
                    .order_by(EventLog.created_at.asc())
                    .all()
                )
            for event in events:
                if event.id <= last_id:
                    continue
                payload = _dump_event_payload(event)
                yield f"data: {payload}\n\n"
                last_id = event.id
            time.sleep(1)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get("/runs/{run_id}/events", response_model=list[EventLogResponse])
def list_run_events(run_id: str, db: DbSession) -> list[EventLogResponse]:
    get_run(db, run_id)
    events = (
        db.query(EventLog)
        .filter(EventLog.run_id == run_id)
        .order_by(EventLog.created_at.asc())
        .all()
    )
    return [EventLogResponse.model_validate(serialize_event_log(event)) for event in events]


@router.get("/runs/{run_id}/artifacts")
def get_run_artifacts(run_id: str, db: DbSession) -> list[dict]:
    get_run(db, run_id)
    return [
        serialize_artifact(artifact, include_content=False)
        for artifact in latest_artifacts(db, run_id)
    ]


@router.get("/runs/{run_id}/artifacts/{artifact_id}")
def get_run_artifact(run_id: str, artifact_id: str, db: DbSession) -> dict:
    get_run(db, run_id)
    artifact = db.get(GeneratedArtifact, artifact_id)
    if artifact is None or artifact.run_id != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return serialize_artifact(artifact, include_content=True)


@router.put("/runs/{run_id}/artifacts/{artifact_id}")
def update_run_artifact(
    run_id: str,
    artifact_id: str,
    payload: UpdateArtifactRequest,
    db: DbSession,
    _: AdminAccess,
) -> dict:
    run = get_run(db, run_id)
    artifact = db.get(GeneratedArtifact, artifact_id)
    if artifact is None or artifact.run_id != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    updated = update_artifact_content(db, run, artifact.path, payload.content)
    db.commit()
    return serialize_artifact(updated, include_content=True)


@router.post("/runs/{run_id}/build", response_model=BuildDeployResponse)
def build_run(run_id: str, db: DbSession, _: AdminAccess) -> BuildDeployResponse:
    get_run(db, run_id)
    enqueue_build(run_id)
    return BuildDeployResponse(run_id=run_id, status="running", message="Build job queued")


@router.post("/runs/{run_id}/deploy", response_model=BuildDeployResponse)
def deploy_run(run_id: str, db: DbSession, _: AdminAccess) -> BuildDeployResponse:
    get_run(db, run_id)
    enqueue_deploy(run_id)
    return BuildDeployResponse(run_id=run_id, status="running", message="Deploy job queued")


@router.post("/runs/{run_id}/approve-deployment", response_model=RunResponse)
def approve_run_deployment(
    run_id: str,
    payload: DeploymentApprovalRequest,
    db: DbSession,
    _: AdminAccess,
) -> RunResponse:
    run = get_run(db, run_id)
    approve_deployment(db, run, notes=payload.notes, approved_by=payload.approved_by)
    log_step(
        db,
        run,
        "approval",
        "completed",
        f"Deployment approved by {payload.approved_by}",
    )
    db.commit()
    return RunResponse.model_validate(serialize_run(run))


@router.post("/runs/{run_id}/test-invocations", response_model=TestInvocationResponse)
def create_test_invocation(
    run_id: str, payload: TestInvocationRequest, db: DbSession, _: AdminAccess
) -> TestInvocationResponse:
    get_run(db, run_id)
    result = invoke_test(
        run_id,
        payload.method,
        payload.path,
        payload.payload,
        payload.headers,
        payload.operation_id,
    )
    return TestInvocationResponse.model_validate(result)


@router.get("/runs/{run_id}/event-artifacts")
def get_event_artifacts(run_id: str, db: DbSession) -> dict:
    run = get_run(db, run_id)
    syncs = (
        db.query(EventPortalSync)
        .filter(EventPortalSync.run_id == run_id)
        .order_by(EventPortalSync.created_at.asc())
        .all()
    )
    return {
        "canonicalModel": run.canonical_model_json,
        "portalSyncs": [serialize_portal_sync(sync) for sync in syncs],
    }


@router.get("/settings", response_model=SettingsView)
def get_settings_view_endpoint(db: DbSession, _: AdminAccess) -> SettingsView:
    return SettingsView.model_validate(settings_view(db))


@router.put("/settings", response_model=SettingsView)
def update_settings_endpoint(
    payload: SettingsUpdateRequest,
    db: DbSession,
    _: AdminAccess,
) -> SettingsView:
    update_settings(db, payload.model_dump())
    db.commit()
    return SettingsView.model_validate(settings_view(db))
