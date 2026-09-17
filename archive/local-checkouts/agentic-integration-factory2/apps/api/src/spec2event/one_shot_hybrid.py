from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx

from spec2event.adapters.build.ecr_docker import EcrDockerBuildEngine
from spec2event.adapters.deploy.ephemeral_ec2 import EphemeralEc2DeploymentAdapter
from spec2event.adapters.portal.solace_event_portal import SolaceEventPortalAdapter
from spec2event.config import get_settings
from spec2event.services.aws_service import AwsService
from spec2event.services.database_generator_service import database_generator_service
from spec2event.services.database_service import canonicalize_database, discover_database_source
from spec2event.services.generator_service import generator_service
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)

HybridRunMode = Literal["generate", "validate", "full"]
RUN_MODES: tuple[HybridRunMode, ...] = ("generate", "validate", "full")
DEFAULT_APPLICATION_DOMAIN_NAME = "Commerce Source Integrations"
DEFAULT_TOPIC_ROOT = "commerce"
DEFAULT_PREFERRED_TABLE = "products"


@dataclass
class HybridSourceBundle:
    raw_spec: str
    openapi_summary: dict[str, Any]
    openapi_model: dict[str, Any]
    database_discovery: dict[str, Any]
    database_model: dict[str, Any]
    application_domain_name: str = DEFAULT_APPLICATION_DOMAIN_NAME
    topic_root: str = DEFAULT_TOPIC_ROOT


@dataclass
class VerificationResult:
    response_status: int
    correlation_id: str | None
    response_payload: dict[str, Any]
    solace_message: dict[str, Any] | None
    consumer_validation: dict[str, Any] | None


@dataclass
class ExecutionResult:
    name: str
    service_name: str
    workspace_path: str
    validation_status: str = "skipped"
    validation_message: str | None = None
    image_tag: str | None = None
    service_url: str | None = None
    build_status: str = "skipped"
    deploy_status: str = "skipped"
    verification: VerificationResult | None = None
    portal_status: str = "skipped"
    portal_items: list[dict[str, Any]] = field(default_factory=list)
    deployment_metadata: dict[str, Any] = field(default_factory=dict)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate or execute the prepared Stripe and PostgreSQL hybrid "
            "micro-integrations."
        )
    )
    parser.add_argument(
        "--mode",
        choices=RUN_MODES,
        default="full",
        help="Run only generation, generation plus local validation, or the full deploy flow.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    summary = run(args.mode)
    print(json.dumps(summary, indent=2))


def run(mode: HybridRunMode = "full") -> dict[str, Any]:
    settings = get_settings()
    _load_env_file(settings.repo_root / ".env")

    if mode == "full":
        _ensure_target_supported()
        _ensure_node_bridge_dependencies(settings.repo_root)

    batch_id = f"hybrid-one-shot-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    batch_dir = settings.runs_root / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    source_bundle = _discover_sources()
    _persist_source_bundle(batch_dir, source_bundle)

    openapi_result, postgres_result = _generate_workspaces(batch_id, source_bundle)

    if mode in {"validate", "full"}:
        _validate_integration(Path(openapi_result.workspace_path), openapi_result)
        _validate_integration(Path(postgres_result.workspace_path), postgres_result)

    if mode == "full":
        _run_full_flow(
            settings=settings,
            batch_dir=batch_dir,
            source_bundle=source_bundle,
            openapi_result=openapi_result,
            postgres_result=postgres_result,
        )

    deployment_target = os.getenv("DEPLOYMENT_TARGET", "ec2")
    summary = _build_summary(
        mode=mode,
        batch_id=batch_id,
        deployment_target=deployment_target,
        source_bundle=source_bundle,
        openapi_result=openapi_result,
        postgres_result=postgres_result,
    )
    _write_json(batch_dir / "summary.json", summary)
    _write_markdown_summary(
        batch_dir / "summary.md",
        mode=mode,
        deployment_target=deployment_target,
        source_bundle=source_bundle,
        openapi_result=openapi_result,
        postgres_result=postgres_result,
    )
    return summary


def _discover_sources() -> HybridSourceBundle:
    openapi_path = Path(_required_env("SOURCE_OPENAPI_FILE"))
    raw_spec = openapi_path.read_text(encoding="utf-8")
    openapi_document = load_openapi_document(raw_spec)
    openapi_summary = summarize_openapi(openapi_document)
    openapi_model = canonicalize_openapi(openapi_document)
    openapi_model["applicationDomainName"] = DEFAULT_APPLICATION_DOMAIN_NAME
    openapi_model["title"] = "Stripe Webhook Source"
    _rebase_topics(openapi_model, DEFAULT_TOPIC_ROOT)

    database_discovery = discover_database_source(
        database_url=os.getenv("SOURCE_DATABASE_URL"),
        host=os.getenv("SOURCE_DATABASE_HOST"),
        port=int(os.getenv("SOURCE_DATABASE_PORT", "5432")),
        database_name=os.getenv("SOURCE_DATABASE_NAME"),
        username=os.getenv("SOURCE_DATABASE_USERNAME"),
        password=os.getenv("SOURCE_DATABASE_PASSWORD"),
        schema=os.getenv("SOURCE_DATABASE_SCHEMA", "public"),
        preferred_table=DEFAULT_PREFERRED_TABLE,
        sslmode=os.getenv("SOURCE_DATABASE_SSLMODE", "require"),
    )
    database_model = canonicalize_database(
        database_discovery,
        application_domain_name=DEFAULT_APPLICATION_DOMAIN_NAME,
        topic_root=DEFAULT_TOPIC_ROOT,
    )

    return HybridSourceBundle(
        raw_spec=raw_spec,
        openapi_summary=openapi_summary,
        openapi_model=openapi_model,
        database_discovery=database_discovery,
        database_model=database_model,
    )


def _persist_source_bundle(batch_dir: Path, source_bundle: HybridSourceBundle) -> None:
    _write_json(batch_dir / "openapi-summary.json", source_bundle.openapi_summary)
    _write_json(batch_dir / "openapi-canonical-model.json", source_bundle.openapi_model)
    _write_json(batch_dir / "postgres-discovery.json", source_bundle.database_discovery)
    _write_json(batch_dir / "postgres-canonical-model.json", source_bundle.database_model)


def _generate_workspaces(
    batch_id: str, source_bundle: HybridSourceBundle
) -> tuple[ExecutionResult, ExecutionResult]:
    openapi_run_id = f"{batch_id}-openapi"
    postgres_run_id = f"{batch_id}-postgres"

    openapi_workspace = generator_service.generate(
        openapi_run_id,
        source_bundle.openapi_model,
        source_bundle.openapi_summary,
        source_bundle.raw_spec,
    )
    postgres_workspace = database_generator_service.generate(
        postgres_run_id,
        source_bundle.database_model,
        source_bundle.database_discovery,
    )

    return (
        ExecutionResult(
            name="openapi",
            service_name=source_bundle.openapi_model["serviceName"],
            workspace_path=str(openapi_workspace),
        ),
        ExecutionResult(
            name="postgres",
            service_name=source_bundle.database_model["serviceName"],
            workspace_path=str(postgres_workspace),
        ),
    )


def _validate_integration(workspace: Path, result: ExecutionResult) -> None:
    result.validation_message = _validate_workspace(workspace)
    result.validation_status = "completed"


def _run_full_flow(
    *,
    settings,
    batch_dir: Path,
    source_bundle: HybridSourceBundle,
    openapi_result: ExecutionResult,
    postgres_result: ExecutionResult,
) -> None:
    aws_service = AwsService(settings)
    build_engine = EcrDockerBuildEngine(aws_service)
    deploy_adapter = EphemeralEc2DeploymentAdapter(aws_service)
    portal_adapter = SolaceEventPortalAdapter(
        base_url=os.getenv("EVENT_PORTAL_BASE_URL"),
        token=os.getenv("EVENT_PORTAL_TOKEN"),
    )
    repository_uri = aws_service.ensure_ecr_repository()
    batch_id = batch_dir.name
    batch_suffix = batch_id[-8:]

    _execute_integration(
        batch_dir=batch_dir,
        name="openapi",
        run_id=f"{batch_id}-openapi",
        result=openapi_result,
        canonical_model=source_bundle.openapi_model,
        image_tag=f"{repository_uri}:{source_bundle.openapi_model['serviceName']}-{batch_suffix}",
        runtime_env=_openapi_runtime_env(),
        build_engine=build_engine,
        deploy_adapter=deploy_adapter,
        portal_adapter=portal_adapter,
        verify=lambda service_url: _verify_openapi(service_url, source_bundle.openapi_model),
    )
    _execute_integration(
        batch_dir=batch_dir,
        name="postgres",
        run_id=f"{batch_id}-postgres",
        result=postgres_result,
        canonical_model=source_bundle.database_model,
        image_tag=f"{repository_uri}:{source_bundle.database_model['serviceName']}-{batch_suffix}",
        runtime_env=_database_runtime_env(),
        build_engine=build_engine,
        deploy_adapter=deploy_adapter,
        portal_adapter=portal_adapter,
        verify=lambda service_url: _verify_database(service_url, source_bundle.database_model),
    )


def _build_summary(
    *,
    mode: HybridRunMode,
    batch_id: str,
    deployment_target: str,
    source_bundle: HybridSourceBundle,
    openapi_result: ExecutionResult,
    postgres_result: ExecutionResult,
) -> dict[str, Any]:
    return {
        "batchId": batch_id,
        "generatedAt": datetime.now(UTC).isoformat(),
        "mode": mode,
        "applicationDomainName": source_bundle.application_domain_name,
        "deploymentTarget": deployment_target,
        "openapi": asdict(openapi_result),
        "postgres": asdict(postgres_result),
    }


def _execute_integration(
    *,
    batch_dir: Path,
    name: str,
    run_id: str,
    result: ExecutionResult,
    canonical_model: dict[str, Any],
    image_tag: str,
    runtime_env: dict[str, str],
    build_engine: EcrDockerBuildEngine,
    deploy_adapter: EphemeralEc2DeploymentAdapter,
    portal_adapter: SolaceEventPortalAdapter,
    verify: Callable[[str], VerificationResult],
) -> None:
    integration_dir = batch_dir / name
    integration_dir.mkdir(parents=True, exist_ok=True)

    build_result = build_engine.build(Path(result.workspace_path), image_tag)
    result.build_status = build_result.status
    result.image_tag = build_result.image_tag
    _write_text(integration_dir / "build.log", build_result.logs or "")
    if build_result.status != "completed" or not build_result.image_tag:
        raise RuntimeError(f"{name} build failed: {build_result.message}")

    deploy_result = deploy_adapter.deploy(
        Path(result.workspace_path),
        build_result.image_tag,
        runtime_env,
        run_id,
    )
    result.deploy_status = deploy_result.status
    result.service_url = deploy_result.service_url
    result.deployment_metadata = deploy_result.metadata or {}
    _write_text(integration_dir / "deploy.log", deploy_result.logs or "")
    if deploy_result.status != "completed" or not deploy_result.service_url:
        raise RuntimeError(f"{name} deploy failed: {deploy_result.message}")

    verification = verify(deploy_result.service_url)
    result.verification = verification
    _write_json(integration_dir / "verification.json", asdict(verification))

    portal_result = portal_adapter.sync(canonical_model)
    result.portal_status = portal_result.status
    result.portal_items = [_portal_item(item) for item in portal_result.items]
    _write_json(
        integration_dir / "event-portal-sync.json",
        {
            "status": portal_result.status,
            "message": portal_result.message,
            "items": result.portal_items,
        },
    )


def _verify_openapi(service_url: str, canonical_model: dict[str, Any]) -> VerificationResult:
    fixture = canonical_model["testFixtures"][0]

    def invoke() -> dict[str, Any]:
        response = httpx.request(
            fixture["method"],
            f"{service_url.rstrip('/')}{fixture['path']}",
            json=fixture["payload"],
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        return {
            "status": response.status_code,
            "payload": _safe_json(response),
        }

    invocation, message = _capture_solace_message(canonical_model["topics"], invoke)
    payload = invocation["payload"]
    return VerificationResult(
        response_status=invocation["status"],
        correlation_id=payload.get("correlationId"),
        response_payload=payload,
        solace_message=message,
        consumer_validation=_validate_consumer_observation(canonical_model, invocation, message),
    )


def _verify_database(service_url: str, canonical_model: dict[str, Any]) -> VerificationResult:
    fixture = canonical_model["testFixtures"][0]

    def invoke() -> dict[str, Any]:
        response = httpx.post(
            f"{service_url.rstrip('/')}{fixture['path']}",
            json=fixture["payload"],
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        return {
            "status": response.status_code,
            "payload": _safe_json(response),
        }

    invocation, message = _capture_solace_message(canonical_model["topics"], invoke)
    payload = invocation["payload"]
    return VerificationResult(
        response_status=invocation["status"],
        correlation_id=payload.get("correlationId"),
        response_payload=payload,
        solace_message=message,
        consumer_validation=_validate_consumer_observation(canonical_model, invocation, message),
    )


def _capture_solace_message(
    topics: list[str],
    invoke: Callable[[], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    process = _start_bridge(topics)
    try:
        _wait_for_bridge_ready(process, timeout=30.0)
        invocation = invoke()
        correlation_id = invocation["payload"].get("correlationId")
        message = _wait_for_bridge_message(process, correlation_id, timeout=45.0)
        return invocation, message
    finally:
        process.terminate()
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()


def _start_bridge(topics: list[str]) -> subprocess.Popen[str]:
    settings = get_settings()
    bridge_path = (
        settings.repo_root
        / "apps"
        / "api"
        / "src"
        / "spec2event"
        / "adapters"
        / "live"
        / "solace_bridge_node.js"
    )
    return subprocess.Popen(
        ["node", str(bridge_path)],
        cwd=str(settings.repo_root),
        env={
            **os.environ,
            "SOLACE_TOPICS_JSON": json.dumps(topics),
            "SOLACE_BROKER_URL": _required_env("SOLACE_BROKER_URL"),
            "SOLACE_VPN": _required_env("SOLACE_VPN"),
            "SOLACE_USERNAME": _required_env("SOLACE_USERNAME"),
            "SOLACE_PASSWORD": _required_env("SOLACE_PASSWORD"),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _wait_for_bridge_ready(process: subprocess.Popen[str], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = _read_bridge_event(process, timeout=1.0)
        if event is None:
            continue
        if event.get("type") == "ready":
            return
        if event.get("type") == "error":
            raise RuntimeError(f"Solace bridge failed: {event}")
    raise TimeoutError("Solace bridge did not become ready")


def _wait_for_bridge_message(
    process: subprocess.Popen[str],
    correlation_id: str | None,
    timeout: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = _read_bridge_event(process, timeout=1.0)
        if event is None:
            continue
        if event.get("type") != "message":
            continue
        if correlation_id is None or event.get("correlationId") == correlation_id:
            return event
    return None


def _read_bridge_event(
    process: subprocess.Popen[str], timeout: float
) -> dict[str, Any] | None:
    if process.stdout is None:
        return None
    if process.poll() is not None:
        output = process.stdout.read()
        raise RuntimeError(f"Solace bridge exited early: {output}")
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        return None
    line = process.stdout.readline()
    if not line:
        return None
    return json.loads(line)


def _validate_workspace(workspace: Path) -> str:
    for command in (
        ["mvn", "-q", "test"],
        ["mvn", "-q", "-DskipTests", "package"],
    ):
        try:
            completed = subprocess.run(
                command,
                cwd=workspace,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Maven is required to validate {workspace.name}: {exc}") from exc
        if completed.returncode != 0:
            raise RuntimeError(
                f"{workspace.name} validation failed for {' '.join(command)}:\n"
                f"{completed.stdout}\n{completed.stderr}"
            )
    return "Validated with mvn test and mvn -DskipTests package."


def _openapi_runtime_env() -> dict[str, str]:
    return {
        "SOLACE_BROKER_URL": _required_env("SOLACE_BROKER_URL"),
        "SOLACE_VPN": _required_env("SOLACE_VPN"),
        "SOLACE_USERNAME": _required_env("SOLACE_USERNAME"),
        "SOLACE_PASSWORD": _required_env("SOLACE_PASSWORD"),
    }


def _database_runtime_env() -> dict[str, str]:
    return {
        **_openapi_runtime_env(),
        "SOURCE_DATABASE_HOST": _required_env("SOURCE_DATABASE_HOST"),
        "SOURCE_DATABASE_PORT": os.getenv("SOURCE_DATABASE_PORT", "5432"),
        "SOURCE_DATABASE_NAME": _required_env("SOURCE_DATABASE_NAME"),
        "SOURCE_DATABASE_USERNAME": _required_env("SOURCE_DATABASE_USERNAME"),
        "SOURCE_DATABASE_PASSWORD": _required_env("SOURCE_DATABASE_PASSWORD"),
        "SOURCE_DATABASE_SSLMODE": os.getenv("SOURCE_DATABASE_SSLMODE", "require"),
        "SOURCE_DATABASE_FETCH_SIZE": "5",
        "SOURCE_DATABASE_POLL_INTERVAL_SECONDS": "60",
        "SOURCE_DATABASE_INITIAL_DELAY_SECONDS": "300",
    }


def _rebase_topics(canonical_model: dict[str, Any], topic_root: str) -> None:
    topics: set[str] = set()
    for operation in canonical_model.get("operations", []):
        for candidate in operation.get("eventCandidates", []):
            candidate["topicName"] = _replace_topic_root(candidate["topicName"], topic_root)
            topics.add(candidate["topicName"])
    canonical_model["topics"] = sorted(topics)


def _replace_topic_root(topic_name: str, topic_root: str) -> str:
    if "/" not in topic_name:
        return f"{topic_root}/{topic_name}"
    _, remainder = topic_name.split("/", 1)
    return f"{topic_root}/{remainder}"


def _portal_item(item: Any) -> dict[str, Any]:
    return {
        "artifactType": item.artifact_type,
        "artifactName": item.artifact_name,
        "status": item.status,
        "externalId": item.external_id,
        "manualAction": item.manual_action,
    }


def _validate_consumer_observation(
    canonical_model: dict[str, Any],
    invocation: dict[str, Any],
    message: dict[str, Any] | None,
) -> dict[str, Any]:
    if not message:
        return {
            "status": "missing_message",
            "messageCaptured": False,
        }

    envelope = message.get("payload") if isinstance(message, dict) else None
    meta = envelope.get("meta") if isinstance(envelope, dict) else {}
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    topic_name = message.get("topicName")
    correlation_id = invocation["payload"].get("correlationId")
    required_headers = canonical_model.get("headerContract", {}).get("requiredHeaders", [])
    missing_metadata = [
        header for header in required_headers if _meta_value(meta, header) in (None, "")
    ]

    candidates = {
        candidate["canonicalEventName"]: candidate
        for operation in canonical_model.get("operations", [])
        for candidate in operation.get("eventCandidates", [])
    }
    matched_event = candidates.get(meta.get("eventType"))
    topic_matched = bool(matched_event and matched_event["topicName"] == topic_name)
    schema_matched = bool(
        matched_event
        and matched_event["schemaName"] == meta.get("schemaName")
        and matched_event.get("schemaSubject") == meta.get("schemaSubject")
    )
    correlation_matched = correlation_id is not None and meta.get("correlationId") == correlation_id
    payload_present = payload is not None

    return {
        "status": (
            "completed"
            if topic_matched and schema_matched and correlation_matched and not missing_metadata
            else "partial"
        ),
        "messageCaptured": True,
        "topicMatched": topic_matched,
        "schemaMatched": schema_matched,
        "correlationMatched": correlation_matched,
        "payloadPresent": payload_present,
        "matchedEventName": meta.get("eventType"),
        "matchedTopicName": topic_name,
        "missingMetadata": missing_metadata,
    }


def _meta_value(meta: dict[str, Any], header_name: str) -> Any:
    if not isinstance(meta, dict):
        return None
    mapping = {
        "content-type": "contentType",
        "event-type": "eventType",
        "schema-name": "schemaName",
        "schema-version": "schemaVersion",
        "source-system": "sourceSystem",
        "source-record-id": "sourceRecordId",
        "correlation-id": "correlationId",
        "occurred-at": "occurredAt",
    }
    return meta.get(mapping.get(header_name, header_name))


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"raw": response.text}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _write_markdown_summary(
    path: Path,
    *,
    mode: HybridRunMode,
    deployment_target: str,
    source_bundle: HybridSourceBundle,
    openapi_result: ExecutionResult,
    postgres_result: ExecutionResult,
) -> None:
    lines = [
        "# Hybrid One-Shot Run",
        "",
        "## Run Summary",
        "",
        f"- Mode: `{mode}`",
        f"- Event Portal domain: `{source_bundle.application_domain_name}`",
        f"- Intended deployment target: `{deployment_target}`",
        "",
        "## Discovery Summary",
        "",
        (
            f"- OpenAPI service: `{source_bundle.openapi_summary['serviceName']}` with "
            f"{source_bundle.openapi_summary['operationCount']} operations"
        ),
        (
            f"- PostgreSQL source: "
            f"`{source_bundle.database_discovery['selectedTableQualifiedName']}` with "
            f"{source_bundle.database_discovery['rowCount']:,} rows"
        ),
        "",
        "## Runtime Summary",
        "",
        *_result_lines("OpenAPI", openapi_result),
        *_result_lines("PostgreSQL", postgres_result),
    ]

    if mode == "full":
        lines.extend(
            [
                "",
                "## Runtime Verification",
                "",
                (
                    f"- OpenAPI consumer verification: "
                    f"`{_verification_status(openapi_result)}`"
                ),
                (
                    f"- PostgreSQL consumer verification: "
                    f"`{_verification_status(postgres_result)}`"
                ),
                "",
                "## Deployment Summary",
                "",
                f"- OpenAPI URL: `{openapi_result.service_url}`",
                f"- PostgreSQL URL: `{postgres_result.service_url}`",
            ]
        )
    elif mode == "validate":
        lines.extend(
            [
                "",
                "## Validation Summary",
                "",
                "- Both runtimes were generated and validated locally.",
                "- Build, deployment, Solace verification, and Event Portal sync were skipped.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Generation Summary",
                "",
                "- Both runtimes were generated from the prepared Stripe and PostgreSQL sources.",
                (
                    "- Local validation, build, deployment, Solace verification, "
                    "and Event Portal sync were skipped."
                ),
            ]
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _result_lines(label: str, result: ExecutionResult) -> list[str]:
    lines = [
        f"- {label} workspace: `{result.workspace_path}`",
        f"- {label} validation: `{result.validation_status}`",
        f"- {label} build: `{result.build_status}`",
        f"- {label} deploy: `{result.deploy_status}`",
        f"- {label} Event Portal: `{result.portal_status}`",
    ]
    if result.image_tag:
        lines.append(f"- {label} image: `{result.image_tag}`")
    if result.service_url:
        lines.append(f"- {label} URL: `{result.service_url}`")
    return lines


def _verification_status(result: ExecutionResult) -> str:
    if result.verification is None:
        return "skipped"
    validation = result.verification.consumer_validation or {}
    return str(validation.get("status", "unknown"))


def _load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key, value)


def _ensure_target_supported() -> None:
    target = os.getenv("DEPLOYMENT_TARGET", "ec2")
    if target not in {"ec2", "ephemeral_ec2"}:
        raise ValueError(f"One-shot hybrid runner only supports EC2 demo targets, got {target}")


def _ensure_node_bridge_dependencies(repo_root: Path) -> None:
    if (repo_root / "node_modules" / "solclientjs").exists():
        return
    completed = subprocess.run(
        ["npm", "install"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "npm install failed while preparing the Solace live bridge:\n"
            f"{completed.stdout}\n{completed.stderr}"
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value in (None, ""):
        raise ValueError(f"Missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    main()
