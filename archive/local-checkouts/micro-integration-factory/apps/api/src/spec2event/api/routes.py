from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from spec2event.adapters.source.registry import available_source_types, get_source_adapter
from spec2event.config import get_settings as app_settings
from spec2event.db import SessionLocal, get_db
from spec2event.models import (
    BuilderSession,
    EventLog,
    EventPortalSync,
    GeneratedArtifact,
    GenerationRun,
    WorkerJob,
)
from spec2event.schemas import (
    BuildDeployResponse,
    BuilderSessionResponse,
    CapturedEventResponse,
    ChatMessageRequest,
    CreateBuilderSessionRequest,
    CreateRunRequest,
    EventLogResponse,
    GenerateBuilderResponse,
    InputMessageRequest,
    LiteLlmTestRequest,
    LiteLlmTestResponse,
    PreviewResponse,
    RunResponse,
    SchemaPackCreateRequest,
    SchemaPackResponse,
    SchemaPackSummaryResponse,
    SettingsUpdateRequest,
    SettingsView,
    SolaceSubscriptionRequest,
    SolaceSubscriptionResponse,
    TestInvocationRequest,
    TestInvocationResponse,
    UpdateArtifactRequest,
    UploadPreviewResponse,
    WorkerJobResponse,
    WorkerJobResultRequest,
)
from spec2event.security import require_admin
from spec2event.services.builder_service import (
    _chat_completion_url,
    add_chat_turn,
    create_builder_session,
    create_manual_input_event,
    create_preview,
    generate_micro_integration,
    get_builder_session,
    redesign_session,
    serialize_builder_session,
    serialize_captured_event,
    serialize_worker_job,
    start_local_worker_if_enabled,
    update_worker_job_result,
)
from spec2event.services.pipeline import invoke_test
from spec2event.services.queue_service import enqueue_build, enqueue_deploy, enqueue_generation
from spec2event.services.run_service import (
    create_run,
    create_upload,
    get_run,
    get_upload,
    latest_artifacts,
    serialize_artifact,
    serialize_event_log,
    serialize_portal_sync,
    serialize_run,
    update_artifact_content,
)
from spec2event.services.schema_pack_service import (
    create_schema_pack,
    delete_schema_pack,
    get_schema_pack,
    list_schema_packs,
    serialize_schema_pack,
)
from spec2event.services.settings_service import get_secret, settings_view, update_settings
from spec2event.services.solace_capture_service import (
    capture_manager,
    events_for_subscription,
    stream_subscription_events,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
AdminAccess = Annotated[None, Depends(require_admin)]
UploadSpecFile = Annotated[UploadFile, File(...)]
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
TRANSFORM_ARTIFACT_DIR = "src/main/resources/transforms/"
TRANSFORM_ARTIFACT_NAMES = {"transform.md", "transform.groovy", "transform.dwl"}


def _dump_run_payload(run: GenerationRun) -> str:
    payload = RunResponse.model_validate(serialize_run(run))
    return json.dumps(payload.model_dump(by_alias=True))


def _dump_event_payload(event: EventLog) -> str:
    payload = EventLogResponse.model_validate(serialize_event_log(event))
    return json.dumps(payload.model_dump(by_alias=True))


def _safe_download_filename(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "._-" else "-"
        for character in value
    )
    return safe.strip("-") or "micro-integration"


def _transform_artifact(db: Session, run_id: str) -> GeneratedArtifact:
    for artifact in latest_artifacts(db, run_id):
        path = artifact.path
        if (
            path.startswith(TRANSFORM_ARTIFACT_DIR)
            and Path(path).name in TRANSFORM_ARTIFACT_NAMES
        ):
            return artifact
    raise HTTPException(status_code=404, detail="Transform artifact not found")


def _completed_worker_for_run(db: Session, run_id: str) -> WorkerJob:
    job = (
        db.query(WorkerJob)
        .join(BuilderSession, WorkerJob.builder_session_id == BuilderSession.id)
        .filter(BuilderSession.generated_run_id == run_id)
        .order_by(WorkerJob.updated_at.desc())
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Worker job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Image export is not ready")
    return job


@router.get("/source-types")
def list_source_types() -> list[str]:
    return available_source_types()


@router.post("/schema-packs", response_model=SchemaPackResponse)
def create_schema_pack_endpoint(
    payload: SchemaPackCreateRequest,
    db: DbSession,
    _: AdminAccess,
) -> SchemaPackResponse:
    pack = create_schema_pack(
        db,
        name=payload.name,
        schema_format=payload.schema_format,
        version=payload.version,
        message_type=payload.message_type,
        industry=payload.industry,
        raw_content=payload.raw_content,
        filename=payload.filename,
        content_type=payload.content_type,
    )
    db.commit()
    return SchemaPackResponse.model_validate(serialize_schema_pack(pack, include_raw=True))


@router.get("/schema-packs", response_model=list[SchemaPackSummaryResponse])
def list_schema_packs_endpoint(db: DbSession) -> list[SchemaPackSummaryResponse]:
    return [
        SchemaPackSummaryResponse.model_validate(serialize_schema_pack(pack, include_raw=False))
        for pack in list_schema_packs(db)
    ]


@router.get("/schema-packs/{schema_pack_id}", response_model=SchemaPackResponse)
def get_schema_pack_endpoint(schema_pack_id: str, db: DbSession) -> SchemaPackResponse:
    pack = get_schema_pack(db, schema_pack_id)
    return SchemaPackResponse.model_validate(serialize_schema_pack(pack, include_raw=True))


@router.delete("/schema-packs/{schema_pack_id}", status_code=204)
def delete_schema_pack_endpoint(
    schema_pack_id: str,
    db: DbSession,
    _: AdminAccess,
) -> Response:
    delete_schema_pack(db, schema_pack_id)
    db.commit()
    return Response(status_code=204)


@router.post("/solace/subscriptions", response_model=SolaceSubscriptionResponse)
def create_solace_subscription(
    payload: SolaceSubscriptionRequest,
    db: DbSession,
    _: AdminAccess,
) -> SolaceSubscriptionResponse:
    state = capture_manager.start(
        db,
        broker_url=payload.broker_url,
        vpn=payload.vpn,
        username=payload.username,
        password=payload.password,
        topic_filter=payload.topic_filter,
    )
    db.commit()
    return SolaceSubscriptionResponse(
        id=state.id,
        topic_filter=state.topic_filter,
        status=state.status,
        message=state.message,
    )


@router.get("/solace/subscriptions/{subscription_id}/events")
def stream_solace_subscription_events(subscription_id: str, db: DbSession) -> StreamingResponse:
    del db
    return StreamingResponse(
        stream_subscription_events(subscription_id),
        media_type="text/event-stream",
        headers=STREAM_HEADERS,
    )


@router.get(
    "/solace/subscriptions/{subscription_id}/captured-events",
    response_model=list[CapturedEventResponse],
)
def list_solace_subscription_events(
    subscription_id: str, db: DbSession
) -> list[CapturedEventResponse]:
    return [
        CapturedEventResponse.model_validate(event)
        for event in events_for_subscription(db, subscription_id)
    ]


@router.post("/builder/input-events", response_model=CapturedEventResponse)
def create_builder_input_event(
    payload: InputMessageRequest,
    db: DbSession,
    _: AdminAccess,
) -> CapturedEventResponse:
    event = create_manual_input_event(
        db,
        topic_name=payload.topic_name,
        input_format=payload.input_format,
        payload=payload.payload,
        source_name=payload.source_name,
        headers=payload.headers,
    )
    db.commit()
    return CapturedEventResponse.model_validate(serialize_captured_event(event))


@router.post("/builder/sessions", response_model=BuilderSessionResponse)
def create_builder_session_endpoint(
    payload: CreateBuilderSessionRequest,
    db: DbSession,
    _: AdminAccess,
) -> BuilderSessionResponse:
    session = create_builder_session(
        db,
        captured_event_id=payload.captured_event_id,
        transform_language=payload.transform_language,
    )
    db.commit()
    return BuilderSessionResponse.model_validate(serialize_builder_session(session))


@router.get("/builder/sessions/{builder_session_id}", response_model=BuilderSessionResponse)
def get_builder_session_endpoint(
    builder_session_id: str, db: DbSession
) -> BuilderSessionResponse:
    session = get_builder_session(db, builder_session_id)
    return BuilderSessionResponse.model_validate(serialize_builder_session(session))


@router.post(
    "/builder/sessions/{builder_session_id}/design",
    response_model=BuilderSessionResponse,
)
def redesign_builder_session(
    builder_session_id: str,
    payload: ChatMessageRequest,
    db: DbSession,
    _: AdminAccess,
) -> BuilderSessionResponse:
    session = redesign_session(
        db,
        builder_session_id=builder_session_id,
        content=payload.content,
        transform_language=payload.transform_language,
        schema_context=payload.schema_context,
        schema_pack_id=payload.schema_pack_id,
    )
    db.commit()
    return BuilderSessionResponse.model_validate(serialize_builder_session(session))


@router.post(
    "/builder/sessions/{builder_session_id}/messages",
    response_model=BuilderSessionResponse,
)
def create_builder_message(
    builder_session_id: str,
    payload: ChatMessageRequest,
    db: DbSession,
    _: AdminAccess,
) -> BuilderSessionResponse:
    session = add_chat_turn(
        db,
        builder_session_id=builder_session_id,
        content=payload.content,
        transform_language=payload.transform_language,
        schema_context=payload.schema_context,
        schema_pack_id=payload.schema_pack_id,
    )
    db.commit()
    return BuilderSessionResponse.model_validate(serialize_builder_session(session))


@router.post("/builder/sessions/{builder_session_id}/preview", response_model=PreviewResponse)
def create_builder_preview(
    builder_session_id: str,
    db: DbSession,
    _: AdminAccess,
) -> PreviewResponse:
    preview = create_preview(db, builder_session_id=builder_session_id)
    db.commit()
    return PreviewResponse.model_validate(preview)


@router.post(
    "/builder/sessions/{builder_session_id}/generate",
    response_model=GenerateBuilderResponse,
)
def generate_builder_micro_integration(
    builder_session_id: str,
    db: DbSession,
    _: AdminAccess,
) -> GenerateBuilderResponse:
    session, run, job = generate_micro_integration(db, builder_session_id=builder_session_id)
    db.commit()
    start_local_worker_if_enabled(
        job.id,
        job.project_path or "",
        run.service_name or "micro-integration",
    )
    return GenerateBuilderResponse(
        session=BuilderSessionResponse.model_validate(serialize_builder_session(session)),
        run=RunResponse.model_validate(serialize_run(run)),
        worker_job=WorkerJobResponse.model_validate(serialize_worker_job(job)),
    )


@router.get("/worker/jobs/{worker_job_id}", response_model=WorkerJobResponse)
def get_worker_job(worker_job_id: str, db: DbSession) -> WorkerJobResponse:
    job = db.get(WorkerJob, worker_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Worker job not found")
    return WorkerJobResponse.model_validate(serialize_worker_job(job))


@router.post("/worker/jobs/{worker_job_id}/result", response_model=WorkerJobResponse)
def update_worker_job_result_endpoint(
    worker_job_id: str,
    payload: WorkerJobResultRequest,
    db: DbSession,
    _: AdminAccess,
) -> WorkerJobResponse:
    job = update_worker_job_result(
        db,
        worker_job_id=worker_job_id,
        status=payload.status,
        logs=payload.logs,
        image_tag=payload.image_tag,
        project_path=payload.project_path,
        result=payload.result,
    )
    db.commit()
    return WorkerJobResponse.model_validate(serialize_worker_job(job))


@router.post("/uploads", response_model=UploadPreviewResponse)
async def upload_source(
    file: UploadSpecFile,
    db: DbSession,
    _: AdminAccess,
    source_type: str = Form("openapi"),
) -> UploadPreviewResponse:
    if source_type not in available_source_types():
        raise HTTPException(status_code=400, detail=f"Unknown source_type: {source_type}")
    adapter = get_source_adapter(source_type)
    raw_bytes = await file.read()
    raw_content = raw_bytes.decode("utf-8")
    parse_result = adapter.parse(raw_content)
    summary_result = adapter.summarize(parse_result.document)
    upload = create_upload(
        db,
        file.filename or "source-input",
        file.content_type or "application/octet-stream",
        raw_content,
        summary_result.summary,
        source_type=source_type,
    )
    db.commit()
    return UploadPreviewResponse(
        upload_id=upload.id,
        filename=upload.filename,
        source_type=source_type,
        service_name=summary_result.service_name,
        summary=summary_result.summary,
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


@router.get("/runs/{run_id}/workspace.zip")
def download_run_workspace(run_id: str, db: DbSession) -> Response:
    run = get_run(db, run_id)
    if not run.workspace_path:
        raise HTTPException(status_code=404, detail="Workspace not generated")
    workspace = Path(run.workspace_path)
    if not workspace.exists():
        raise HTTPException(status_code=404, detail="Workspace not found")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(workspace.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(workspace).as_posix())
    filename = f"{run.service_name or 'micro-integration'}-vscode-project.zip"
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/transform-file")
def download_run_transform_file(run_id: str, db: DbSession) -> Response:
    run = get_run(db, run_id)
    artifact = _transform_artifact(db, run.id)
    filename = f"{_safe_download_filename(run.service_name)}-{Path(artifact.path).name}"
    return Response(
        artifact.content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs/{run_id}/image.tar")
def download_run_image(run_id: str, db: DbSession) -> FileResponse:
    run = get_run(db, run_id)
    job = _completed_worker_for_run(db, run.id)
    image_tag = job.image_tag or run.image_tag
    if not image_tag:
        raise HTTPException(status_code=404, detail="Docker image tag not found")
    docker_path = shutil.which("docker")
    if not docker_path:
        raise HTTPException(status_code=503, detail="Docker CLI is not available")
    inspect = subprocess.run(
        [docker_path, "image", "inspect", image_tag],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if inspect.returncode != 0:
        raise HTTPException(
            status_code=404,
            detail=f"Docker image is not available: {image_tag}",
        )
    handle = tempfile.NamedTemporaryFile(
        prefix="micro-integration-image-",
        suffix=".tar",
        delete=False,
    )
    handle.close()
    save = subprocess.run(
        [docker_path, "save", "-o", handle.name, image_tag],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    if save.returncode != 0:
        try:
            os.unlink(handle.name)
        except FileNotFoundError:
            pass
        raise HTTPException(
            status_code=500,
            detail=save.stderr or save.stdout or "Docker image export failed",
        )
    filename = f"{_safe_download_filename(run.service_name)}-image.tar"
    return FileResponse(
        handle.name,
        media_type="application/x-tar",
        filename=filename,
        background=BackgroundTask(os.unlink, handle.name),
    )


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


@router.post("/settings/litellm/test", response_model=LiteLlmTestResponse)
def test_litellm_settings_endpoint(
    payload: LiteLlmTestRequest,
    db: DbSession,
    _: AdminAccess,
) -> LiteLlmTestResponse:
    base_url = payload.litellm_base_url or get_secret(db, "litellm_base_url")
    api_key = payload.litellm_api_key or get_secret(db, "litellm_api_key")
    model = (
        payload.litellm_model
        or get_secret(db, "litellm_model")
        or app_settings().litellm_model
    )
    if not base_url or not api_key or not model:
        return LiteLlmTestResponse(
            ok=False,
            message="LiteLLM base URL, API key, and model are required.",
            model=model,
        )
    try:
        response = httpx.post(
            _chat_completion_url(base_url),
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with ok."}],
                "temperature": 0,
                "max_tokens": 8,
            },
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        response.raise_for_status()
    except Exception as exc:
        return LiteLlmTestResponse(
            ok=False,
            message=f"LiteLLM connection failed: {exc}",
            model=model,
        )
    return LiteLlmTestResponse(ok=True, message="LiteLLM connection succeeded.", model=model)
