from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from spec2event.adapters.ai.litellm import LiteLLMRefinementProvider
from spec2event.adapters.build.ecr_docker import EcrDockerBuildEngine
from spec2event.adapters.build.local_docker import LocalDockerBuildEngine
from spec2event.adapters.deploy.ec2_docker_host import Ec2DockerHostDeploymentAdapter
from spec2event.adapters.deploy.ephemeral_ec2 import EphemeralEc2DeploymentAdapter
from spec2event.adapters.deploy.kubernetes_helm import KubernetesHelmDeploymentAdapter
from spec2event.adapters.deploy.local_docker import LocalDockerDeploymentAdapter
from spec2event.adapters.live.solace_bridge import live_bridge_manager
from spec2event.adapters.portal.solace_event_portal import SolaceEventPortalAdapter
from spec2event.adapters.source.registry import get_source_adapter
from spec2event.config import get_settings
from spec2event.db import session_scope
from spec2event.services.aws_service import AwsService
from spec2event.services.command_runner import run_command
from spec2event.services.generator_service import generator_service
from spec2event.services.run_service import (
    get_run,
    latest_artifacts,
    log_step,
    record_deployment,
    record_event_log,
    record_portal_sync,
    record_test_invocation,
    snapshot_workspace,
    update_artifact_content,
    update_run,
)
from spec2event.services.settings_service import get_secret


def generation_pipeline(run_id: str, auto_build: bool = False, auto_deploy: bool = False) -> None:
    current_step = "uploaded"
    try:
        with session_scope() as db:
            run = get_run(db, run_id)
            upload = run.upload
            update_run(db, run, status="running", last_message="Starting generation pipeline")
            log_step(
                db, run, "uploaded", "completed", f"Source upload accepted ({run.source_type})"
            )
            db.commit()

            current_step = "parsed"
            adapter = get_source_adapter(run.source_type)
            parse_result = adapter.parse(upload.raw_content)
            summary_result = adapter.summarize(parse_result.document)
            summary = summary_result.summary
            upload.summary_json = summary
            log_step(
                db,
                run,
                "parsed",
                "completed",
                f"Parsed source ({run.source_type}): {summary.get('operationCount', 'N/A')} items",
            )
            db.commit()

            current_step = "canonicalized"
            canonical_result = adapter.canonicalize(parse_result.document)
            canonical_model = canonical_result.canonical_model
            update_run(
                db,
                run,
                service_name=canonical_model["serviceName"],
                canonical_model_json=canonical_model,
            )
            log_step(
                db,
                run,
                "canonicalized",
                "completed",
                f"Derived {len(canonical_model['topics'])} topics",
            )
            db.commit()

            current_step = "generated"
            workspace = generator_service.generate(
                run.id,
                canonical_model,
                summary,
                upload.raw_content,
            )
            update_run(db, run, workspace_path=str(workspace))
            snapshot_workspace(db, run, workspace)
            log_step(db, run, "generated", "completed", "Generated MDK project")
            db.commit()

            current_step = "ai_refined"
            log_step(db, run, "ai_refined", "running", "Refining generated artifacts")
            db.commit()
            ai_result = _run_ai_refinement(db, run.id, canonical_model)
            log_step(db, run, "ai_refined", ai_result["status"], ai_result["message"])
            db.commit()

            current_step = "validated"
            validation_message = _validate_workspace(Path(run.workspace_path or workspace))
            log_step(db, run, "validated", "completed", validation_message)
            db.commit()

            current_step = "portal_synced"
            portal_result = _sync_event_portal(db, run.id, canonical_model)
            log_step(db, run, "portal_synced", portal_result["status"], portal_result["message"])

            final_status = "completed"
            if portal_result["status"] in {"partial", "not_configured"}:
                final_status = "partial"
            update_run(db, run, status=final_status, last_message="Generation complete")
            db.commit()
    except Exception as exc:  # noqa: BLE001
        _record_failure(run_id, current_step, exc)
        return

    if auto_build:
        build_pipeline(run_id)
    if auto_deploy:
        if not auto_build:
            build_pipeline(run_id)
        deploy_pipeline(run_id)


def build_pipeline(run_id: str) -> None:
    try:
        with session_scope() as db:
            run = get_run(db, run_id)
            update_run(db, run, status="running", last_message="Building container image")
            log_step(db, run, "built", "running", "Building container image")
            db.commit()

            if not run.workspace_path:
                raise ValueError("Run workspace not generated")
            image_tag = _image_tag_for_run(db, run)
            engine = _build_engine(db, run.deployment_target)
            result = engine.build(Path(run.workspace_path), image_tag)
            run_status = _run_status_after_build(run.status, result.status)
            update_run(
                db,
                run,
                status=run_status,
                last_message=result.message,
                image_tag=result.image_tag,
            )
            log_step(
                db,
                run,
                "built",
                result.status,
                result.message,
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001
        _record_failure(run_id, "built", exc)


def deploy_pipeline(run_id: str) -> None:
    try:
        with session_scope() as db:
            run = get_run(db, run_id)
            update_run(db, run, status="running", last_message="Deploying integration")
            log_step(db, run, "deployed", "running", "Deploying integration")
            db.commit()

            if not run.workspace_path:
                raise ValueError("Run workspace not generated")
            if not run.image_tag:
                raise ValueError("Run image not built")
            runtime_env = _runtime_env(db)
            adapter = _deployment_adapter(db, run.deployment_target)
            result = adapter.deploy(Path(run.workspace_path), run.image_tag, runtime_env, run.id)
            metadata = {**(result.metadata or {})}
            if result.logs:
                metadata.setdefault("logs", result.logs)
            record_deployment(
                db,
                run,
                target=run.deployment_target,
                status=result.status,
                image_tag=run.image_tag,
                service_url=result.service_url,
                metadata_json=metadata,
            )
            update_run(
                db,
                run,
                status="partial" if result.status != "completed" else "completed",
                service_url=result.service_url,
                last_message=result.message,
            )
            log_step(
                db,
                run,
                "deployed",
                result.status,
                result.message,
            )
            db.commit()
            if result.status == "completed" and run.canonical_model_json:
                live_bridge_manager.ensure_subscription(
                    run.id, run.canonical_model_json.get("topics", []), _solace_credentials(db)
                )
                log_step(
                    db,
                    run,
                    "ready",
                    "completed",
                    "Integration deployed and ready for live test",
                )
                db.commit()
    except Exception as exc:  # noqa: BLE001
        _record_failure(run_id, "deployed", exc)


def invoke_test(
    run_id: str,
    method: str,
    path: str,
    payload: dict | None,
    headers: dict[str, str],
    operation_id: str | None,
) -> dict:
    with session_scope() as db:
        run = get_run(db, run_id)
        if not run.service_url:
            raise ValueError("Run is not deployed")
        correlation_id = headers.get("x-correlation-id") or str(uuid.uuid4())
        url = f"{run.service_url.rstrip('/')}{path}"
        record_event_log(
            db, run, correlation_id=correlation_id, stage="request_received", payload_json=payload
        )

    response = httpx.request(
        method.upper(),
        url,
        json=payload,
        headers={**headers, "x-correlation-id": correlation_id},
        timeout=30.0,
    )
    response_payload = _safe_json(response)

    with session_scope() as db:
        run = get_run(db, run_id)
        record_test_invocation(
            db,
            run,
            operation_id=operation_id,
            method=method.upper(),
            request_path=path,
            correlation_id=correlation_id,
            request_payload_json=payload,
            response_status=response.status_code,
            response_payload_json=response_payload,
        )
        record_event_log(
            db,
            run,
            correlation_id=correlation_id,
            stage="integration_execution",
            payload_json=response_payload,
        )
        for topic_name in (
            response_payload.get("publishedTopics", [])
            if isinstance(response_payload, dict)
            else []
        ):
            record_event_log(
                db,
                run,
                correlation_id=correlation_id,
                stage="event_published",
                topic_name=topic_name,
                payload_json=response_payload,
            )

    return {
        "invocationId": str(uuid.uuid4()),
        "correlationId": correlation_id,
        "responseStatus": response.status_code,
        "responsePayload": response_payload,
    }


def _run_ai_refinement(db, run_id: str, canonical_model: dict) -> dict[str, str]:
    run = get_run(db, run_id)
    configured_model = get_secret(db, "litellm_model")
    candidate_models = []
    for model in [configured_model, "bedrock-claude-4-5-sonnet-tools"]:
        if model and model not in candidate_models:
            candidate_models.append(model)

    last_result = None
    for index, model in enumerate(candidate_models, start=1):
        artifacts = {artifact.path: artifact.content for artifact in latest_artifacts(db, run_id)}
        provider = LiteLLMRefinementProvider(
            base_url=get_secret(db, "litellm_base_url"),
            api_key=get_secret(db, "litellm_api_key"),
            model=model,
        )
        result = provider.refine(canonical_model, artifacts)
        last_result = result
        if result.applied:
            accepted_patches, skipped_java_paths = _filter_unsafe_ai_patches(
                result.patches[:20], artifacts
            )
            if not accepted_patches:
                last_result = AiRefinementResultShim(
                    status="completed",
                    message=_no_op_ai_message(model, skipped_java_paths),
                )
                continue

            original_contents = {
                patch.path: artifacts[patch.path]
                for patch in accepted_patches
                if patch.path in artifacts
            }
            for patch in accepted_patches:
                update_artifact_content(db, run, patch.path, patch.content)

            java_patch_paths = [
                patch.path for patch in accepted_patches if patch.path.endswith(".java")
            ]
            compile_validation = {"status": "completed", "message": "AI patches passed validation"}
            if java_patch_paths:
                compile_validation = _validate_ai_patch_set(Path(run.workspace_path or ""), model)
            if compile_validation["status"] != "completed":
                for path in java_patch_paths:
                    content = original_contents.get(path)
                    if content is None:
                        continue
                    update_artifact_content(db, run, path, content)
                db.commit()
                last_result = AiRefinementResultShim(
                    status="completed",
                    message=_compile_revert_message(
                        model=model,
                        kept_safe_patches=bool(
                            accepted_patches and len(java_patch_paths) != len(accepted_patches)
                        ),
                    ),
                )
                continue
            message = _applied_ai_message(
                model=model,
                accepted_patches=accepted_patches,
                skipped_java_paths=skipped_java_paths,
                used_fallback=index > 1,
            )
            return {"status": result.status, "message": message}
        if result.status == "not_configured":
            return {"status": result.status, "message": result.message}
        if result.status in {"completed", "partial"}:
            return {"status": result.status, "message": result.message}

    if last_result is None:
        return {"status": "not_configured", "message": "AI refinement is not configured"}
    return {
        "status": last_result.status,
        "message": last_result.message,
    }


def _sync_event_portal(db, run_id: str, canonical_model: dict) -> dict[str, str]:
    adapter = SolaceEventPortalAdapter(
        base_url=get_secret(db, "event_portal_base_url"),
        token=get_secret(db, "event_portal_token"),
    )
    result = adapter.sync(canonical_model)
    run = get_run(db, run_id)
    for item in result.items:
        record_portal_sync(
            db,
            run,
            artifact_type=item.artifact_type,
            artifact_name=item.artifact_name,
            status=item.status,
            external_id=item.external_id,
            manual_action=item.manual_action,
            request_payload_json=item.request_payload,
            response_payload_json=item.response_payload,
        )
    return {"status": result.status, "message": result.message}


def _record_failure(run_id: str, step_name: str, exc: Exception) -> None:
    message = str(exc) or type(exc).__name__
    with session_scope() as db:
        run = get_run(db, run_id)
        update_run(db, run, status="failed", last_message=message)
        log_step(db, run, step_name, "failed", message)


def _validate_workspace(workspace: Path) -> str:
    required = [
        workspace / "pom.xml",
        workspace / "Dockerfile",
        workspace / "src/main/java/com/spec2event/generated/MicroIntegrationApplication.java",
        workspace / "src/main/resources/application.yml",
        workspace / "helm/Chart.yaml",
    ]
    missing = [str(path.relative_to(workspace)) for path in required if not path.exists()]
    if missing:
        raise ValueError(f"Workspace validation failed; missing files: {missing}")
    return "Static validation passed for required generated files"


def _validate_ai_patch_set(workspace: Path, model: str) -> dict[str, str]:
    if not workspace.exists():
        return {
            "status": "failed",
            "message": f"AI patches from {model} were rejected because the workspace is missing",
        }
    try:
        result = run_command(["mvn", "-q", "-DskipTests", "compile"], cwd=workspace)
    except FileNotFoundError as exc:
        message = (
            f"AI patches from {model} could not be validated because Maven is unavailable: {exc}"
        )
        return {
            "status": "failed",
            "message": message,
        }

    if result.returncode == 0:
        return {"status": "completed", "message": "AI patches passed Java compile validation"}

    return {
        "status": "failed",
        "message": (
            f"AI refinement from {model} failed validation and was reverted. "
            "Continuing with the baseline project."
        ),
    }


def _filter_unsafe_ai_patches(
    patches,
    artifacts: dict[str, str],
) -> tuple[list, list[str]]:
    safe_patches = []
    skipped_java_paths: list[str] = []
    for patch in patches:
        if patch.path.endswith("CanonicalEventService.java"):
            required_signatures = ["planForOperation("]
            if any(signature not in patch.content for signature in required_signatures):
                skipped_java_paths.append(patch.path)
                continue
        safe_patches.append(patch)
    return safe_patches, skipped_java_paths


def _compile_revert_message(*, model: str, kept_safe_patches: bool) -> str:
    if kept_safe_patches:
        return (
            f"AI refinement from {model} kept safe docs and config improvements, "
            "but baseline runtime code was preserved after validation."
        )
    return (
        f"AI refinement from {model} did not pass validation, so the generated project "
        "was kept unchanged."
    )


def _no_op_ai_message(model: str, skipped_java_paths: list[str]) -> str:
    if skipped_java_paths:
        filenames = ", ".join(Path(path).name for path in skipped_java_paths)
        return (
            f"AI refinement from {model} proposed unsafe runtime changes for {filenames}, "
            "so the generated project was kept unchanged."
        )
    return f"AI refinement from {model} did not produce any safe changes."


def _applied_ai_message(
    *,
    model: str,
    accepted_patches,
    skipped_java_paths: list[str],
    used_fallback: bool,
) -> str:
    categories: list[str] = []
    if any(patch.path.endswith(".md") for patch in accepted_patches):
        categories.append("docs")
    if any(patch.path.endswith((".yml", ".yaml", ".json")) for patch in accepted_patches):
        categories.append("config")
    if any(patch.path.endswith(".java") for patch in accepted_patches):
        categories.append("runtime code")

    if not categories:
        categories.append("artifacts")

    joined_categories = ", ".join(categories)
    model_note = f" with fallback model {model}" if used_fallback else ""
    message = f"Applied AI refinements to {joined_categories}{model_note}."
    if skipped_java_paths:
        filenames = ", ".join(Path(path).name for path in skipped_java_paths)
        message = f"{message} Kept baseline runtime code for {filenames}."
    return message


class AiRefinementResultShim:
    def __init__(self, *, status: str, message: str) -> None:
        self.status = status
        self.message = message


def _deployment_adapter(db, deployment_target: str):
    if deployment_target == "ephemeral_ec2":
        return EphemeralEc2DeploymentAdapter()
    if deployment_target == "ec2_docker_host":
        return Ec2DockerHostDeploymentAdapter(
            host=get_secret(db, "deploy_ec2_host") or "",
            ssh_user=get_secret(db, "deploy_ec2_ssh_user") or "ec2-user",
            ssh_private_key=get_secret(db, "deploy_ec2_ssh_private_key") or "",
            port=int(get_secret(db, "deploy_ec2_port") or 22),
            public_base_url=get_secret(db, "public_base_url"),
        )
    if deployment_target == "kubernetes_helm":
        return KubernetesHelmDeploymentAdapter()
    return LocalDockerDeploymentAdapter()


def _build_engine(db, deployment_target: str) -> LocalDockerBuildEngine:
    if deployment_target == "ephemeral_ec2":
        return EcrDockerBuildEngine()
    if deployment_target in {"ec2_docker_host", "kubernetes_helm"}:
        return LocalDockerBuildEngine(
            push=True,
            registry=get_secret(db, "container_registry"),
            username=get_secret(db, "container_registry_username"),
            password=get_secret(db, "container_registry_password"),
        )
    return LocalDockerBuildEngine()


def _run_status_after_build(previous_status: str, build_status: str) -> str:
    if build_status == "failed":
        return "failed"
    if build_status == "not_configured":
        return "partial"
    if previous_status == "partial":
        return "partial"
    return "completed"


def _image_tag_for_run(db, run) -> str:
    settings = get_settings()
    if run.deployment_target == "ephemeral_ec2":
        repository_uri = AwsService(settings).ensure_ecr_repository()
        return f"{repository_uri}:{run.service_name}-{run.id[:8]}"
    return f"{settings.container_image_prefix}/{run.service_name}:{run.id[:8]}"


def _runtime_env(db) -> dict[str, str]:
    keys = [
        "solace_broker_url",
        "solace_vpn",
        "solace_username",
        "solace_password",
        "stripe_webhook_secret",
        "stripe_secret_key",
        "public_base_url",
    ]
    mapping = {
        "solace_broker_url": "SOLACE_BROKER_URL",
        "solace_vpn": "SOLACE_VPN",
        "solace_username": "SOLACE_USERNAME",
        "solace_password": "SOLACE_PASSWORD",
        "stripe_webhook_secret": "STRIPE_WEBHOOK_SECRET",
        "stripe_secret_key": "STRIPE_SECRET_KEY",
        "public_base_url": "PUBLIC_BASE_URL",
    }
    return {mapping[key]: value for key in keys if (value := get_secret(db, key)) not in (None, "")}


def _solace_credentials(db) -> dict[str, str]:
    return {
        "solace_broker_url": get_secret(db, "solace_broker_url") or "",
        "solace_vpn": get_secret(db, "solace_vpn") or "",
        "solace_username": get_secret(db, "solace_username") or "",
        "solace_password": get_secret(db, "solace_password") or "",
    }


def _safe_json(response: httpx.Response) -> dict:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}
    except Exception:
        return {"raw": response.text}
