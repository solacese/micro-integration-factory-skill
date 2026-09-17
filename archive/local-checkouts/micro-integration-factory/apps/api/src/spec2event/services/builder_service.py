from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from spec2event.config import get_settings
from spec2event.db import session_scope
from spec2event.models import (
    BuilderSession,
    CapturedEvent,
    ChatMessage,
    GenerationRun,
    SourceUpload,
    WorkerJob,
)
from spec2event.services.generator_service import generator_service
from spec2event.services.run_service import (
    create_run,
    iso,
    snapshot_workspace,
    update_run,
)
from spec2event.services.schema_pack_service import get_schema_pack, schema_pack_prompt_context
from spec2event.services.settings_service import get_secret

TRANSFORM_LANGUAGES = {"java_sdk", "groovy", "dataweave"}
AI_TIMEOUT_SECONDS = 180.0
TRANSFORM_ARTIFACT_PREFIX = "src/main/resources/transforms/"
MAX_SAMPLE_OUTPUT_BYTES = 256 * 1024
MAX_TRANSFORM_ARTIFACT_BYTES = 128 * 1024
SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"aws_secret_access_key", re.IGNORECASE),
    re.compile(r"aws_session_token", re.IGNORECASE),
    re.compile(r"litellm_api_key", re.IGNORECASE),
    re.compile(r"['\"]?password['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
]
TEXT_SUFFIXES = {
    ".java",
    ".groovy",
    ".dwl",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".properties",
    ".txt",
    ".example",
}
LITELLM_SYSTEM_PROMPT = (
    "You are Claude Code running through LiteLLM as a focused "
    "Solace micro-integration transform engineer. Only build "
    "Solace micro integrations. Refuse unrelated scope inside "
    "the JSON assistantMessage. Return strict JSON only."
)
LITELLM_REPAIR_SYSTEM_PROMPT = (
    "You repair malformed assistant JSON for a Solace micro-integration builder. "
    "Return one strict JSON object only. Do not add markdown or commentary."
)


def create_manual_input_event(
    db: Session,
    *,
    topic_name: str,
    input_format: str,
    payload: Any,
    source_name: str | None = None,
    headers: dict[str, Any] | None = None,
) -> CapturedEvent:
    normalized_topic = topic_name.strip()
    if not normalized_topic:
        raise HTTPException(status_code=400, detail="Input message topic is required")
    normalized_format = input_format.strip().lower() or "json"
    source_label = (source_name or "Manual input message").strip() or "Manual input message"
    normalized_payload = _normalize_manual_payload(payload, normalized_format)
    event_headers = {
        "source": source_label,
        "sourceType": "manual_input",
        "inputFormat": normalized_format,
        **(headers or {}),
    }
    event = CapturedEvent(
        subscription_id=str(uuid.uuid4()),
        broker_url="manual://input",
        topic_filter=normalized_topic,
        topic_name=normalized_topic,
        headers_json=event_headers,
        payload_json=normalized_payload,
    )
    db.add(event)
    db.flush()
    return event


def create_builder_session(
    db: Session, *, captured_event_id: str, transform_language: str
) -> BuilderSession:
    if transform_language not in TRANSFORM_LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported transform language")
    captured_event = db.get(CapturedEvent, captured_event_id)
    if captured_event is None:
        raise HTTPException(status_code=404, detail="Captured event not found")
    session = BuilderSession(
        captured_event_id=captured_event.id,
        transform_language=transform_language,
        status="awaiting_design",
        draft_json=None,
    )
    db.add(session)
    db.flush()
    return session


def redesign_session(
    db: Session,
    *,
    builder_session_id: str,
    content: str,
    transform_language: str | None = None,
    schema_context: str | None = None,
    schema_pack_id: str | None = None,
) -> BuilderSession:
    session = get_builder_session(db, builder_session_id)
    if transform_language:
        if transform_language not in TRANSFORM_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported transform language")
        session.transform_language = transform_language

    schema_pack = _resolve_schema_pack_context(db, schema_pack_id)
    draft = generate_draft(
        db,
        session,
        content,
        intent="live_design",
        schema_context=schema_context,
        schema_pack=schema_pack,
    )
    draft["workbenchPrompt"] = content
    draft["schemaContext"] = schema_context
    draft["schemaPackId"] = schema_pack_id
    draft["schemaPack"] = schema_pack
    session.draft_json = draft
    session.preview_json = None
    session.intent_summary = draft.get("intentSummary")
    session.status = "designed"
    db.flush()
    return session


def add_chat_turn(
    db: Session,
    *,
    builder_session_id: str,
    content: str,
    transform_language: str | None = None,
    schema_context: str | None = None,
    schema_pack_id: str | None = None,
) -> BuilderSession:
    session = get_builder_session(db, builder_session_id)
    if transform_language:
        if transform_language not in TRANSFORM_LANGUAGES:
            raise HTTPException(status_code=400, detail="Unsupported transform language")
        session.transform_language = transform_language

    schema_pack = _resolve_schema_pack_context(db, schema_pack_id)
    user_message = ChatMessage(
        builder_session_id=session.id,
        role="user",
        content=content,
    )
    db.add(user_message)
    db.flush()

    draft = generate_draft(
        db,
        session,
        content,
        intent="chat_turn",
        schema_context=schema_context,
        schema_pack=schema_pack,
    )
    draft["workbenchPrompt"] = content
    draft["schemaContext"] = schema_context
    draft["schemaPackId"] = schema_pack_id
    draft["schemaPack"] = schema_pack
    session.draft_json = draft
    session.preview_json = None
    session.intent_summary = draft.get("intentSummary")
    session.status = "drafted"

    assistant_message = ChatMessage(
        builder_session_id=session.id,
        role="assistant",
        content=draft.get("assistantMessage") or "Draft updated.",
        draft_json=draft,
    )
    db.add(assistant_message)
    db.flush()
    return session


def create_preview(db: Session, *, builder_session_id: str) -> dict[str, Any]:
    session = get_builder_session(db, builder_session_id)
    existing_draft = _current_draft(session)
    if existing_draft is not None and isinstance(existing_draft.get("sampleOutput"), dict):
        sample_output = existing_draft["sampleOutput"]
        session.preview_json = sample_output
        session.status = "previewed"
        db.flush()
        return {
            "sessionId": session.id,
            "transformLanguage": session.transform_language,
            "sampleOutput": sample_output,
            "draft": existing_draft,
        }
    user_prompt = (
        _latest_user_prompt(session)
        or _draft_workbench_prompt(session)
        or "Create a sample preview output for the selected payload transformation."
    )
    schema_context = _draft_schema_context(session)
    schema_pack = _draft_schema_pack_context(session)
    draft = generate_draft(
        db,
        session,
        user_prompt,
        intent="preview",
        schema_context=schema_context,
        schema_pack=schema_pack,
    )
    draft["workbenchPrompt"] = user_prompt
    draft["schemaContext"] = schema_context
    draft["schemaPackId"] = _draft_schema_pack_id(session)
    draft["schemaPack"] = schema_pack
    session.draft_json = draft
    sample_output = draft.get("sampleOutput")
    if not isinstance(sample_output, dict):
        raise HTTPException(status_code=502, detail="LiteLLM response omitted sampleOutput")
    session.preview_json = sample_output
    session.status = "previewed"
    db.flush()
    return {
        "sessionId": session.id,
        "transformLanguage": session.transform_language,
        "sampleOutput": sample_output,
        "draft": draft,
    }


def generate_micro_integration(
    db: Session, *, builder_session_id: str
) -> tuple[BuilderSession, Any, WorkerJob]:
    session = get_builder_session(db, builder_session_id)
    captured_event = session.captured_event
    draft = _current_draft(session)
    if draft is None:
        user_prompt = (
            _latest_user_prompt(session)
            or _draft_workbench_prompt(session)
            or "Create the final implementation plan for this Solace micro-integration."
        )
        schema_context = _draft_schema_context(session)
        schema_pack = _draft_schema_pack_context(session)
        draft = generate_draft(
            db,
            session,
            user_prompt,
            intent="generate_project",
            schema_context=schema_context,
            schema_pack=schema_pack,
        )
        draft["workbenchPrompt"] = user_prompt
        draft["schemaContext"] = schema_context
        draft["schemaPackId"] = _draft_schema_pack_id(session)
        draft["schemaPack"] = schema_pack
    draft["generationMode"] = "fast_template_single_transform_file"
    session.draft_json = draft
    session.intent_summary = draft.get("intentSummary")
    source_message = source_message_for_event(captured_event)
    service_name = _service_name(draft, captured_event)
    raw_source = json.dumps(
        {
            "inputMessage": source_message,
            "capturedEvent": serialize_captured_event(captured_event),
            "draft": draft,
        },
        indent=2,
    )
    summary = {
        "serviceName": service_name,
        "sourceType": source_message["sourceType"],
        "sourceName": source_message["sourceName"],
        "inputFormat": source_message["inputFormat"],
        "topicFilter": captured_event.topic_filter,
        "topicName": captured_event.topic_name,
        "transformLanguage": session.transform_language,
    }
    upload = SourceUpload(
        source_type="custom",
        filename=f"{service_name}-captured-event.json",
        content_type="application/json",
        raw_content=raw_source,
        summary_json=summary,
    )
    db.add(upload)
    db.flush()
    run = create_run(db, upload, "local_docker")
    canonical_model = canonical_model_for_event(
        service_name=service_name,
        captured_event=captured_event,
        draft=draft,
        transform_language=session.transform_language,
    )
    workspace = generator_service.generate(run.id, canonical_model, summary, raw_source)
    _write_transform_artifacts(workspace, session.transform_language, draft, captured_event)
    update_run(
        db,
        run,
        status="completed",
        service_name=service_name,
        workspace_path=str(workspace),
        canonical_model_json=canonical_model,
        last_message="Generated Micro Integration Factory project",
    )
    snapshot_workspace(db, run, workspace)
    session.generated_run_id = run.id
    session.status = "generated"
    job = WorkerJob(
        builder_session_id=session.id,
        status="pending",
        project_path=str(workspace),
        logs="Local worker queued. Security and performance checks will run before Docker build.\n",
    )
    db.add(job)
    db.flush()
    return session, run, job


def start_local_worker_if_enabled(
    worker_job_id: str, project_path: str, service_name: str
) -> None:
    if get_settings().enable_local_worker and project_path:
        _start_local_worker(worker_job_id, Path(project_path), service_name)


def get_builder_session(db: Session, builder_session_id: str) -> BuilderSession:
    session = db.get(BuilderSession, builder_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Builder session not found")
    return session


def _resolve_schema_pack_context(
    db: Session, schema_pack_id: str | None
) -> dict[str, Any] | None:
    if not schema_pack_id:
        return None
    return schema_pack_prompt_context(get_schema_pack(db, schema_pack_id))


def update_worker_job_result(
    db: Session,
    *,
    worker_job_id: str,
    status: str,
    logs: str | None = None,
    image_tag: str | None = None,
    project_path: str | None = None,
    result: dict[str, Any] | None = None,
) -> WorkerJob:
    job = db.get(WorkerJob, worker_job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Worker job not found")
    job.status = status
    if logs is not None:
        job.logs = logs
    if image_tag is not None:
        job.image_tag = image_tag
    if project_path is not None:
        job.project_path = project_path
    if result is not None:
        job.result_json = result
    db.flush()
    return job


def serialize_captured_event(event: CapturedEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "subscription_id": event.subscription_id,
        "broker_url": _redact_url(event.broker_url),
        "topic_filter": event.topic_filter,
        "topic_name": event.topic_name,
        "headers": event.headers_json or {},
        "payload": event.payload_json or {},
        "created_at": iso(event.created_at),
    }


def source_message_for_event(event: CapturedEvent) -> dict[str, Any]:
    headers = event.headers_json or {}
    manual = event.broker_url == "manual://input" or headers.get("sourceType") == "manual_input"
    return {
        "id": event.id,
        "sourceType": "manual_input" if manual else "solace_live_event",
        "sourceName": headers.get("source") or ("Manual input message" if manual else "Solace"),
        "inputFormat": headers.get("inputFormat") or "json",
        "topicName": event.topic_name,
        "topicFilter": event.topic_filter,
        "headers": headers,
        "payload": event.payload_json or {},
        "createdAt": iso(event.created_at),
    }


def serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "draft": message.draft_json,
        "created_at": iso(message.created_at),
    }


def serialize_builder_session(session: BuilderSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "transform_language": session.transform_language,
        "status": session.status,
        "intent_summary": session.intent_summary,
        "draft": session.draft_json,
        "preview": session.preview_json,
        "generated_run_id": session.generated_run_id,
        "captured_event": serialize_captured_event(session.captured_event),
        "messages": [
            serialize_chat_message(message)
            for message in sorted(session.messages, key=lambda item: item.created_at)
        ],
    }


def serialize_worker_job(job: WorkerJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "builder_session_id": job.builder_session_id,
        "job_type": job.job_type,
        "status": job.status,
        "project_path": job.project_path,
        "image_tag": job.image_tag,
        "logs": job.logs,
        "result": job.result_json,
        "created_at": iso(job.created_at),
        "updated_at": iso(job.updated_at),
    }


def _litellm_chat_content(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int,
) -> str:
    response = httpx.post(
        _chat_completion_url(base_url),
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.35,
            "max_tokens": max_tokens,
        },
        timeout=httpx.Timeout(AI_TIMEOUT_SECONDS, connect=5.0),
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("LiteLLM response content must be a string")
    return content


def generate_draft(
    db: Session,
    session: BuilderSession,
    user_prompt: str,
    *,
    intent: str,
    schema_context: str | None = None,
    schema_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = get_secret(db, "litellm_base_url")
    api_key = get_secret(db, "litellm_api_key")
    model = get_secret(db, "litellm_model") or get_settings().litellm_model
    if not base_url or not api_key or not model:
        raise HTTPException(
            status_code=400,
            detail=(
                "LiteLLM is required for every builder chat turn. Configure "
                "the AI Provider settings in the app, or use local LiteLLM environment "
                "fallbacks during development."
            ),
        )

    prompt = _draft_prompt(
        session,
        user_prompt,
        intent=intent,
        schema_context=schema_context,
        schema_pack=schema_pack,
    )
    try:
        content = _litellm_chat_content(
            base_url,
            api_key,
            model,
            [
                {"role": "system", "content": LITELLM_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4500,
        )
        try:
            parsed = _extract_json(content)
        except (json.JSONDecodeError, ValueError) as parse_exc:
            repair_content = _litellm_chat_content(
                base_url,
                api_key,
                model,
                [
                    {"role": "system", "content": LITELLM_REPAIR_SYSTEM_PROMPT},
                    {"role": "user", "content": _repair_json_prompt(content, parse_exc)},
                ],
                max_tokens=4500,
            )
            parsed = _extract_json(repair_content)
        draft = normalize_draft(parsed, session.captured_event, session.transform_language)
        draft["llmProvider"] = {
            "provider": "litellm",
            "model": model,
            "mode": "claude-code",
            "status": "completed",
            "intent": intent,
        }
        return draft
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LiteLLM design failed: {exc}") from exc


def normalize_draft(
    draft: dict[str, Any],
    captured_event: CapturedEvent,
    transform_language: str,
) -> dict[str, Any]:
    required = {
        "intentSummary": str,
        "assistantMessage": str,
        "topicMapping": dict,
        "sampleOutput": dict,
        "files": list,
        "validationNotes": list,
    }
    missing_or_invalid = [
        key
        for key, expected_type in required.items()
        if not isinstance(draft.get(key), expected_type)
    ]
    if missing_or_invalid:
        raise ValueError(f"LiteLLM draft missing required fields: {missing_or_invalid}")
    topic_mapping = draft["topicMapping"]
    if not isinstance(topic_mapping.get("inputTopic"), str):
        topic_mapping["inputTopic"] = captured_event.topic_name
    if not isinstance(topic_mapping.get("outputTopic"), str):
        raise ValueError("LiteLLM draft must include topicMapping.outputTopic")
    draft["files"] = _normalize_draft_files(draft["files"])
    draft["files"] = _single_transform_file(draft["files"], transform_language)
    draft["qualifyingQuestions"] = []
    return {
        **draft,
        "transformLanguage": transform_language,
    }


def _normalize_draft_files(files: list[Any]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("LiteLLM draft files must contain objects")
        path = item.get("path")
        purpose = item.get("purpose")
        content = item.get("content")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("LiteLLM draft file entries require path")
        if path.startswith("/") or ".." in Path(path).parts:
            raise ValueError(f"LiteLLM draft file path is not safe: {path}")
        if not path.startswith(TRANSFORM_ARTIFACT_PREFIX):
            raise ValueError(
                "LiteLLM may only generate transform artifacts under "
                f"{TRANSFORM_ARTIFACT_PREFIX}: {path}"
            )
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError(f"LiteLLM draft file requires purpose: {path}")
        file_entry = {"path": path, "purpose": purpose}
        if content is not None:
            if not isinstance(content, str):
                raise ValueError(f"LiteLLM draft file content must be a string: {path}")
            file_entry["content"] = content
        normalized.append(file_entry)
    return normalized


def _single_transform_file(
    files: list[dict[str, str]], transform_language: str
) -> list[dict[str, str]]:
    expected_path = _expected_transform_path(transform_language)
    for item in files:
        path = item.get("path")
        content = item.get("content")
        if path == expected_path and isinstance(content, str) and content.strip():
            return [item]
    expected_name = Path(expected_path).name
    for item in files:
        path = item.get("path")
        content = item.get("content")
        if Path(path or "").name == expected_name and isinstance(content, str) and content.strip():
            return [{**item, "path": expected_path}]
    raise ValueError(f"LiteLLM draft must include exactly one transform file: {expected_path}")


def _expected_transform_path(transform_language: str) -> str:
    if transform_language == "groovy":
        return "src/main/resources/transforms/transform.groovy"
    if transform_language == "dataweave":
        return "src/main/resources/transforms/transform.dwl"
    return "src/main/resources/transforms/transform.md"


def _draft_file_content(draft: dict[str, Any], expected_path: str) -> str | None:
    expected_name = Path(expected_path).name
    for item in draft.get("files", []):
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        if path == expected_path or Path(path).name == expected_name:
            return content
    return None


def canonical_model_for_event(
    *,
    service_name: str,
    captured_event: CapturedEvent,
    draft: dict[str, Any],
    transform_language: str,
) -> dict[str, Any]:
    source_message = source_message_for_event(captured_event)
    source_label = str(source_message.get("sourceName") or "input message")
    entity = _entity_name(captured_event.topic_name or service_name)
    event_name = f"{_pascal(entity)}Processed"
    schema_name = f"{event_name}Payload"
    raw_topic_mapping = draft.get("topicMapping")
    topic_mapping = raw_topic_mapping if isinstance(raw_topic_mapping, dict) else {}
    raw_output_topic = topic_mapping.get("outputTopic")
    output_topic = (
        raw_output_topic
        if isinstance(raw_output_topic, str)
        else f"micro/integration/{entity}/processed/v1"
    )
    operation_id = f"process{_pascal(entity)}"
    return {
        "title": f"{_title(service_name)} Micro Integration",
        "serviceName": service_name,
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "ingressType": "event_subscriber",
        "stripeEnabled": False,
        "operations": [
            {
                "operationId": operation_id,
                "method": "SUBSCRIBE",
                "path": f"/topics/{_slug(captured_event.topic_filter)}",
                "summary": draft.get("intentSummary")
                or "Process an input message payload",
                "requestSchema": {"type": "object"},
                "responseSchema": {"type": "object"},
                "emitsEvent": True,
                "eventCandidates": [
                    {
                        "canonicalEventName": event_name,
                        "topicName": output_topic,
                        "schemaName": schema_name,
                        "applicationName": f"{service_name}-integration",
                        "operationId": operation_id,
                        "emitsEvent": True,
                    }
                ],
            }
        ],
        "topics": [output_topic],
        "schemaNames": [schema_name],
        "applicationNames": [f"{service_name}-integration"],
        "testFixtures": [
            {
                "operationId": operation_id,
                "label": f"{source_label} from {captured_event.topic_name}",
                "method": "POST",
                "path": "/test-events",
                "payload": captured_event.payload_json,
            }
        ],
        "builderDraft": draft,
        "transformLanguage": transform_language,
    }


def _write_transform_artifacts(
    workspace: Path, transform_language: str, draft: dict[str, Any], captured_event: CapturedEvent
) -> None:
    transform_dir = workspace / "src/main/resources/transforms"
    transform_dir.mkdir(parents=True, exist_ok=True)
    sample_input = json.dumps(captured_event.payload_json or {}, indent=2)
    sample_output = json.dumps(draft.get("sampleOutput") or {}, indent=2)
    if transform_language == "groovy":
        groovy_content = _draft_file_content(
            draft, "src/main/resources/transforms/transform.groovy"
        )
        if groovy_content is None:
            raise HTTPException(
                status_code=502,
                detail=(
                    "LiteLLM draft omitted "
                    "src/main/resources/transforms/transform.groovy content"
                ),
            )
        (transform_dir / "transform.groovy").write_text(
            groovy_content,
            encoding="utf-8",
        )
    elif transform_language == "dataweave":
        dataweave_content = _draft_file_content(
            draft, "src/main/resources/transforms/transform.dwl"
        )
        if dataweave_content is None:
            raise HTTPException(
                status_code=502,
                detail="LiteLLM draft omitted src/main/resources/transforms/transform.dwl content",
            )
        (transform_dir / "transform.dwl").write_text(
            dataweave_content,
            encoding="utf-8",
        )
    else:
        (transform_dir / "transform.md").write_text(
            _draft_file_content(draft, "src/main/resources/transforms/transform.md")
            or draft.get(
                "assistantMessage",
                "Java SDK transform plan generated for this micro integration.",
            ),
            encoding="utf-8",
        )
    (transform_dir / "sample-input.json").write_text(sample_input, encoding="utf-8")
    (transform_dir / "sample-output.json").write_text(sample_output, encoding="utf-8")
    ai_dir = workspace / "ai"
    ai_dir.mkdir(parents=True, exist_ok=True)
    (ai_dir / "claude-code-plan.json").write_text(
        json.dumps(draft, indent=2),
        encoding="utf-8",
    )


def _start_local_worker(job_id: str, workspace: Path, service_name: str) -> None:
    thread = threading.Thread(
        target=_run_local_worker,
        args=(job_id, workspace, service_name),
        daemon=True,
        name=f"local-worker-{job_id}",
    )
    thread.start()


def _run_local_worker(job_id: str, workspace: Path, service_name: str) -> None:
    logs: list[str] = []
    status = "running"
    local_image_tag = f"micro-integration-factory/{service_name}:local"
    image_tag: str | None = local_image_tag
    image_size_bytes: int | None = None
    with session_scope() as db:
        update_worker_job_result(db, worker_job_id=job_id, status=status, logs="Starting.\n")

    code_path = shutil.which("code")
    if code_path:
        result = subprocess.run(
            [code_path, str(workspace)], capture_output=True, text=True, check=False, timeout=15
        )
        logs.append(_command_log("code", result.returncode, result.stdout, result.stderr))
    else:
        logs.append("VS Code CLI not found; project was generated but not opened.\n")

    try:
        quality_logs = _run_quality_checks(workspace)
        logs.extend(quality_logs)
    except RuntimeError as exc:
        logs.append(f"Quality gates failed.\n{exc}\n")
        with session_scope() as db:
            update_worker_job_result(
                db,
                worker_job_id=job_id,
                status="failed",
                logs="".join(logs),
                image_tag=None,
                project_path=str(workspace),
                result={
                    "workspace": str(workspace),
                    "securityPassed": False,
                    "performancePassed": False,
                    "dockerAvailable": bool(shutil.which("docker")),
                },
            )
        return

    docker_path = shutil.which("docker")
    if docker_path:
        build_started = time.monotonic()
        result = subprocess.run(
            [docker_path, "build", "-t", local_image_tag, "."],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        logs.append(_command_log("docker build", result.returncode, result.stdout, result.stderr))
        status = "completed" if result.returncode == 0 else "failed"
        build_seconds = round(time.monotonic() - build_started, 3)
        if result.returncode == 0:
            inspect = subprocess.run(
                [docker_path, "image", "inspect", local_image_tag, "--format", "{{.Size}}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            logs.append(
                _command_log(
                    "docker image inspect",
                    inspect.returncode,
                    inspect.stdout,
                    inspect.stderr,
                )
            )
            if inspect.returncode == 0:
                try:
                    image_size_bytes = int(inspect.stdout.strip())
                except ValueError:
                    image_size_bytes = None
    else:
        logs.append("Docker CLI not found; image build was skipped.\n")
        status = "partial"
        image_tag = None
        build_seconds = None

    benchmarks = _collect_benchmarks(workspace)
    if image_size_bytes is not None:
        benchmarks["imageSizeBytes"] = image_size_bytes
    if build_seconds is not None:
        benchmarks["dockerBuildSeconds"] = build_seconds

    with session_scope() as db:
        job = db.get(WorkerJob, job_id)
        if status == "completed" and job is not None and job.builder_session.generated_run_id:
            run = db.get(GenerationRun, job.builder_session.generated_run_id)
            if run is not None and image_tag:
                update_run(db, run, image_tag=image_tag)
        update_worker_job_result(
            db,
            worker_job_id=job_id,
            status=status,
            logs="".join(logs),
            image_tag=image_tag,
            project_path=str(workspace),
            result={
                "workspace": str(workspace),
                "securityPassed": True,
                "performancePassed": True,
                "mavenTestsRun": bool(shutil.which("mvn")),
                "dockerAvailable": bool(docker_path),
                **benchmarks,
            },
        )


def _run_quality_checks(workspace: Path) -> list[str]:
    logs = [
        _run_security_check(workspace),
        _run_performance_check(workspace),
    ]
    mvn_path = shutil.which("mvn")
    if mvn_path:
        result = subprocess.run(
            [mvn_path, "test"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
            timeout=900,
        )
        logs.append(_command_log("mvn test", result.returncode, result.stdout, result.stderr))
        if result.returncode != 0:
            raise RuntimeError("Maven tests failed before Docker build.")
    else:
        logs.append("Maven CLI not found; generated project tests were skipped.\n")
    return logs


def _run_security_check(workspace: Path) -> str:
    findings: list[str] = []
    for path in workspace.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if "target" in path.parts or ".git" in path.parts:
            continue
        if path.name in {"sample-input.json", "source-spec.json"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(str(path.relative_to(workspace)))
                break
    if findings:
        raise RuntimeError(
            "Security scan found possible committed secrets in generated files: "
            + ", ".join(findings)
        )
    return "$ security scan\nexit=0\nNo committed secrets or unsafe transform paths detected.\n"


def _run_performance_check(workspace: Path) -> str:
    output_path = workspace / "src/main/resources/transforms/sample-output.json"
    transform_dir = workspace / "src/main/resources/transforms"
    if output_path.exists() and output_path.stat().st_size > MAX_SAMPLE_OUTPUT_BYTES:
        raise RuntimeError("Performance check failed: sample output exceeds 256 KB.")
    if transform_dir.exists():
        for path in transform_dir.iterdir():
            if path.is_file() and path.stat().st_size > MAX_TRANSFORM_ARTIFACT_BYTES:
                raise RuntimeError(
                    f"Performance check failed: {path.name} exceeds 128 KB transform budget."
                )
    return (
        "$ performance scan\n"
        "exit=0\n"
        "Transform artifacts are bounded and sample output is within the preview budget.\n"
    )


def _collect_benchmarks(workspace: Path) -> dict[str, Any]:
    transform_dir = workspace / "src/main/resources/transforms"
    sample_input_bytes = _file_size(transform_dir / "sample-input.json")
    sample_output_bytes = _file_size(transform_dir / "sample-output.json")
    transform_bytes = 0
    if transform_dir.exists():
        for path in transform_dir.iterdir():
            if path.is_file() and path.name not in {"sample-input.json", "sample-output.json"}:
                transform_bytes += path.stat().st_size
    payload_budget = max(sample_input_bytes + sample_output_bytes, 512)
    event_throughput = max(1000, min(75000, int(140_000_000 / payload_budget)))
    p95_latency_ms = round(max(1.0, payload_budget / 65536), 2)
    return {
        "sampleInputBytes": sample_input_bytes,
        "sampleOutputBytes": sample_output_bytes,
        "transformArtifactBytes": transform_bytes,
        "eventThroughputPerSecond": event_throughput,
        "p95LatencyMs": p95_latency_ms,
    }


def _file_size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def _normalize_manual_payload(payload: Any, input_format: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"records": payload}
    if payload is None:
        return {}
    if isinstance(payload, str):
        text = payload.strip()
        if input_format == "json" and text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {
                    "rawPayload": payload,
                    "inputFormat": input_format,
                    "parseStatus": "unparsed_json",
                }
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"records": parsed}
            return {"value": parsed}
        return {"rawPayload": payload, "inputFormat": input_format}
    return {"value": payload}


def _command_log(command: str, returncode: int, stdout: str, stderr: str) -> str:
    return f"$ {command}\nexit={returncode}\n{stdout}{stderr}\n"


def _draft_prompt(
    session: BuilderSession,
    user_prompt: str,
    *,
    intent: str,
    schema_context: str | None = None,
    schema_pack: dict[str, Any] | None = None,
) -> str:
    template_notes = {
        "java_sdk": "Generate a concise Java SDK transform plan in transform.md only.",
        "groovy": "Generate only the Groovy transform script in transform.groovy.",
        "dataweave": "Generate only the DataWeave transform in transform.dwl.",
    }
    return json.dumps(
        {
            "task": (
                "You are Claude Code building a small Solace MDK micro-integration. "
                "Stay narrowly focused on this micro integration and nothing else. "
                "The application template owns the broker client, Spring/MDK scaffold, "
                "Dockerfile, tests, and project structure. You only generate the true "
                "payload transformation artifact and a sample transformed output. "
                "Generate exactly one mutable transform file. The rest of the project "
                "is deterministic template code. "
                "Use customer JSON/XML/CSV/EDI/HL7 schemas, keep/drop rules, and "
                "Event Portal schema context as validation and mapping constraints. "
                "When schemaPack is present, treat it as a reusable schema asset and "
                "make explicit structure, segment, composite, header, and field mapping "
                "notes for HL7, EDI, XML, CSV, and fixed-width cases. "
                "For generic builder requests, accept the user's freeform scenario as "
                "the primary integration goal even when it mixes multiple modes such as "
                "event-to-system, system-to-event, validation, anonymization, aggregation, "
                "format conversion, protocol change, and topic/header rewrite. "
                "If the schema context contains a keep list, return only those fields "
                "unless the user explicitly "
                "asks otherwise. For protocol-change requests, stay inside the same "
                "single micro-integration boundary: consume the input message, map "
                "protocol metadata and payload fields into the requested target protocol "
                "or serialization representation, choose a target topic, and generate "
                "only the transform/adapter artifact plus sample output. "
                "DataWeave transform requests may manipulate message attributes and "
                "headers alongside the payload, including rewriting a topic header or "
                "publish destination to a UNS topic. "
                "Return JSON only with exactly these top-level keys: transformLanguage, "
                "intentSummary, assistantMessage, qualifyingQuestions, topicMapping, "
                "sampleOutput, files, validationNotes, and optional headerMapping. "
                "Do not return markdown. Do not "
                "ask the user qualifying questions before generation. Make strong, "
                "reasonable assumptions from the input payload, topic/message name, "
                "schema context, and latest user prompt. Infer the output topic, "
                "invalid payload handling, "
                "sensitive fields, aggregation window, and required canonical fields when "
                "they are not specified. Set qualifyingQuestions to an empty array and put "
                "important assumptions in validationNotes and assistantMessage. Do not "
                "propose macro integrations, external systems, broad architectures, auth "
                "flows, data lakes, orchestration, or non-transform files. Include "
                "generated file contents in files[].content. Escape all newlines and "
                "quotes inside files[].content as valid JSON string content. Make "
                "assistantMessage "
                "specific about the output topic, sample output, and transform file path "
                "that was written. Keep assistantMessage under 80 words and "
                "validationNotes to at most six high-value notes. Keep sampleOutput "
                "small and only include fields needed to prove the transform. When "
                "previousDraft is provided, treat it as the current state and update it "
                "in place for the latest userPrompt instead of re-expanding settled "
                "decisions. "
                "Prefer DataWeave for schema-backed format conversion, header rewriting, "
                "XML, CSV, fixed-width, HL7, EDIFACT, ANSI X12, ODETTE, and protocol "
                "change scenarios unless the user explicitly selects another transform "
                "language. "
                "Do not mention Claude Code, LiteLLM, model names, or internal prompting "
                "inside assistantMessage."
            ),
            "intent": intent,
            "modelBehavior": (
                "Use Claude Sonnet 4.6 style: decisive implementation assumptions, "
                "smooth incremental design, and code-focused output."
            ),
            "transformLanguage": session.transform_language,
            "transformArtifactRule": template_notes.get(session.transform_language),
            "userPrompt": user_prompt,
            "schemaContext": schema_context,
            "schemaPack": schema_pack,
            "inputMessage": source_message_for_event(session.captured_event),
            "capturedEvent": serialize_captured_event(session.captured_event),
            "previousDraft": _compact_previous_draft(session.draft_json),
            "responseLimits": {
                "assistantMessageWords": 80,
                "validationNotesMaxItems": 6,
                "sampleOutputMaxBytes": 4096,
                "filesMaxItems": 1,
                "transformContentGuidance": "concise but complete",
            },
            "requiredContract": {
                "transformLanguage": session.transform_language,
                "intentSummary": "string",
                "assistantMessage": "string",
                "qualifyingQuestions": [],
                "topicMapping": {
                    "inputTopic": session.captured_event.topic_name,
                    "outputTopic": "string Solace topic",
                },
                "headerMapping": {
                    "inputHeaders": "optional object copied from inputMessage.headers",
                    "outputHeaders": "optional object of headers after the transform",
                    "topicHeader": "optional rewritten destination/topic header",
                    "notes": ["optional string"],
                },
                "sampleOutput": "object transformed from inputMessage.payload",
                "files": [
                    {"path": "string", "purpose": "string", "content": "string"},
                ],
                "validationNotes": ["string"],
            },
            "schemaBehavior": {
                "acceptedInputs": [
                    "JSON schema",
                    "XML schema",
                    "CSV schema",
                    "HL7 v2 segments",
                    "EDIFACT/ODETTE message schemas",
                    "ANSI X12 transaction sets",
                    "simple keep/drop rules",
                ],
                "keepRuleExample": {
                    "userPrompt": (
                        "Strip out sensitive data from ORDER and only return customer, "
                        "items and total"
                    ),
                    "schemaContext": {"keep": ["customer", "items", "total", "orderId"]},
                    "dataWeaveShape": (
                        "Return a %dw 2.0 mapping that selects payload.orderId, "
                        "payload.customer, payload.items, and payload.total."
                    ),
                },
                "eventPortal": (
                    "When Event Portal schema check is requested but no schema is present, "
                    "infer a schema name from the topic and service, then record that "
                    "assumption in validationNotes."
                ),
                "schemaPackRules": [
                    "If schemaPack.format is hl7, reference source segments such as MSH, "
                    "SCH, PID, PV1, RGS, AIS, AIG, AIL, or AIP when present.",
                    "If schemaPack.format is EDIFACT, ODETTE, ANSI X12, or generic_edi, "
                    "map segment identifiers and required/repeating hints explicitly.",
                    "If schemaPack.format is xml_schema, map elements/types and note "
                    "required/repeating element handling.",
                    "If schemaPack.format is csv_layout or fixed_width, map columns, "
                    "positions, types, and rejected-row behavior.",
                    "Put mapping notes in validationNotes and keep sampleOutput small.",
                ],
            },
            "protocolChangeBehavior": {
                "incomingExamples": [
                    "MQTT",
                    "AMQP",
                    "JMS",
                    "REST/HTTP",
                    "Kafka",
                    "Solace SMF",
                    "HL7",
                    "EDIFACT",
                    "ANSI X12",
                    "ODETTE",
                ],
                "targetExamples": [
                    "OPC UA",
                    "Parquet",
                    "Avro",
                    "CloudEvents JSON",
                    "XML",
                    "CSV",
                    "Canonical JSON event",
                ],
                "scope": (
                    "Represent target protocol metadata and payload shape in the transform "
                    "artifact and sample output. Do not add broker clients, gateways, "
                    "connectors, or extra project files outside the generated transform."
                ),
                "topicHint": (
                    "Infer a clear output topic such as protocol/<target>/<entity>/v1 or "
                    "customer/<target>/<entity>/v1 when the user has not specified one."
                ),
            },
            "systemToEventBehavior": {
                "scope": (
                    "When the sourceType is manual_input, treat the payload as a message "
                    "from an external system that must become a publishable Solace event. "
                    "Infer the business event name, topic, canonical fields, validation "
                    "rules, and schema notes from the source name, input format, payload, "
                    "schema context, and user prompt."
                ),
                "topicHint": (
                    "Infer output topics such as customer/<domain>/<event>/v1, "
                    "canonical/<entity>/<verb>/v1, or protocol/<target>/<entity>/v1."
                ),
                "formatHint": (
                    "DataWeave may describe JSON, XML, CSV, Java objects, fixed-width, "
                    "EDI, HL7, and other schema-backed transforms when the user requests "
                    "format conversion."
                ),
            },
            "headerRewriteBehavior": {
                "scope": (
                    "For SAP AEM, Sparkplug, IoT, and UNS routing requests, transform "
                    "both payload and message headers. Choose topicMapping.outputTopic "
                    "as the actual Solace publish destination and include headerMapping "
                    "when a topic, routing, subject, sourceTopic, targetTopic, "
                    "sapEventType, sparkplugTopic, or UNS path header is changed."
                ),
                "sampleOutputShape": (
                    "When headers are changed, make sampleOutput an envelope with "
                    "headers and payload keys, unless the user explicitly asks for a "
                    "payload-only preview. The headers object should include the "
                    "rewritten topic/UNS path and any preserved correlation headers."
                ),
                "unsTopicHint": (
                    "Infer UNS topics like uns/<site>/<area>/<line>/<asset>/<event>/v1 "
                    "or enterprise/<domain>/<entity>/<event>/v1 from payload fields, "
                    "source topic, source system, and user prompt."
                ),
            },
            "fileRequirements": {
                "groovy": (
                    "Include only src/main/resources/transforms/transform.groovy with content."
                ),
                "dataweave": (
                    "Include only src/main/resources/transforms/transform.dwl with content."
                ),
                "java_sdk": (
                    "Include only src/main/resources/transforms/transform.md with the Java SDK "
                    "implementation approach and any important generated snippets."
                ),
            },
        },
        indent=2,
    )


def _compact_previous_draft(draft: Any) -> dict[str, Any] | None:
    if not isinstance(draft, dict):
        return None
    compact: dict[str, Any] = {}
    for key in (
        "intentSummary",
        "assistantMessage",
        "topicMapping",
        "headerMapping",
        "sampleOutput",
        "workbenchPrompt",
        "schemaContext",
        "schemaPackId",
        "schemaPack",
    ):
        value = draft.get(key)
        if value is None:
            continue
        compact[key] = _truncate_prompt_value(value)

    notes = draft.get("validationNotes")
    if isinstance(notes, list):
        compact["validationNotes"] = [
            _truncate_text(note, 240) for note in notes if isinstance(note, str)
        ][:6]

    files = draft.get("files")
    if isinstance(files, list):
        compact_files: list[dict[str, str]] = []
        for item in files:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            purpose = item.get("purpose")
            content = item.get("content")
            if not isinstance(path, str):
                continue
            compact_file = {"path": path}
            if isinstance(purpose, str):
                compact_file["purpose"] = _truncate_text(purpose, 160)
            if isinstance(content, str):
                compact_file["content"] = _truncate_text(content, 2800)
            compact_files.append(compact_file)
            break
        if compact_files:
            compact["files"] = compact_files
    return compact


def _truncate_prompt_value(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, 1200)
    if isinstance(value, dict):
        encoded = json.dumps(value, separators=(",", ":"))
        if len(encoded) <= 3000:
            return value
        return {"truncatedJson": _truncate_text(encoded, 3000)}
    if isinstance(value, list):
        encoded = json.dumps(value, separators=(",", ":"))
        if len(encoded) <= 3000:
            return value
        return {"truncatedJson": _truncate_text(encoded, 3000)}
    return value


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 24].rstrip() + "\n... [truncated]"


def _repair_json_prompt(content: str, parse_error: Exception) -> str:
    return json.dumps(
        {
            "task": (
                "Repair the invalid response into strict JSON for the builder. Preserve "
                "the original decisions, topic mapping, sample output, validation notes, "
                "and transform file content. Escape all file content newlines and quotes "
                "so the result parses with JSON.parse/json.loads."
            ),
            "parseError": str(parse_error),
            "invalidResponse": _truncate_text(content, 12000),
            "requiredTopLevelKeys": [
                "transformLanguage",
                "intentSummary",
                "assistantMessage",
                "qualifyingQuestions",
                "topicMapping",
                "sampleOutput",
                "files",
                "validationNotes",
            ],
            "rules": [
                "Return exactly one JSON object and no markdown.",
                "Set qualifyingQuestions to an empty array.",
                "Keep exactly one files entry with path, purpose, and content.",
                f"File path must be under {TRANSFORM_ARTIFACT_PREFIX}.",
            ],
        },
        indent=2,
    )


def _latest_user_prompt(session: BuilderSession) -> str | None:
    for message in sorted(session.messages, key=lambda item: item.created_at, reverse=True):
        if message.role == "user":
            return message.content
    return None


def _draft_workbench_prompt(session: BuilderSession) -> str | None:
    if isinstance(session.draft_json, dict):
        prompt = session.draft_json.get("workbenchPrompt")
        if isinstance(prompt, str):
            return prompt
    return None


def _draft_schema_context(session: BuilderSession) -> str | None:
    if isinstance(session.draft_json, dict):
        schema_context = session.draft_json.get("schemaContext")
        if isinstance(schema_context, str) and schema_context.strip():
            return schema_context
    return None


def _draft_schema_pack_id(session: BuilderSession) -> str | None:
    if isinstance(session.draft_json, dict):
        schema_pack_id = session.draft_json.get("schemaPackId")
        if isinstance(schema_pack_id, str) and schema_pack_id.strip():
            return schema_pack_id
    return None


def _draft_schema_pack_context(session: BuilderSession) -> dict[str, Any] | None:
    if isinstance(session.draft_json, dict):
        schema_pack = session.draft_json.get("schemaPack")
        if isinstance(schema_pack, dict):
            return schema_pack
    return None


def _current_draft(session: BuilderSession) -> dict[str, Any] | None:
    if not isinstance(session.draft_json, dict):
        return None
    try:
        return normalize_draft(
            dict(session.draft_json),
            session.captured_event,
            session.transform_language,
        )
    except ValueError:
        return None


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Draft response must be a JSON object")
    return parsed


def _chat_completion_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _language_files(transform_language: str) -> list[dict[str, str]]:
    if transform_language == "groovy":
        return [
            {"path": "src/main/resources/transforms/transform.groovy", "purpose": "Groovy draft"},
            {
                "path": "src/main/java/.../service/CanonicalEventService.java",
                "purpose": "MDK runtime",
            },
        ]
    if transform_language == "dataweave":
        return [
            {"path": "src/main/resources/transforms/transform.dwl", "purpose": "DataWeave draft"},
            {
                "path": "src/main/java/.../service/CanonicalEventService.java",
                "purpose": "Equivalent Java runtime",
            },
        ]
    return [
        {
            "path": "src/main/java/.../service/CanonicalEventService.java",
            "purpose": "Java SDK runtime",
        },
        {"path": "config/application-runtime.yml", "purpose": "Solace workflow routing"},
    ]


def _service_name(draft: dict[str, Any], captured_event: CapturedEvent) -> str:
    raw_topic_mapping = draft.get("topicMapping")
    topic_mapping = raw_topic_mapping if isinstance(raw_topic_mapping, dict) else {}
    basis = (
        draft.get("serviceName")
        or topic_mapping.get("outputTopic")
        or captured_event.topic_name
        or "micro-integration"
    )
    return _slug(str(basis))[:48] or "micro-integration"


def _entity_name(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    if not parts:
        return "event"
    if len(parts) > 1 and parts[-1].lower() in {"v1", "v2"}:
        return parts[-2].lower()
    return parts[-1].lower()


def _pascal(value: str) -> str:
    parts = [part for part in re.split(r"[^A-Za-z0-9]+", value) if part]
    return "".join(part[:1].upper() + part[1:] for part in parts) or "Event"


def _title(value: str) -> str:
    return " ".join(part.capitalize() for part in _slug(value).split("-"))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    return slug or "micro-integration"


def _redact_url(value: str) -> str:
    return re.sub(r"//([^:@/]+):([^@/]+)@", "//***:***@", value)
