from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from spec2event.config import get_settings
from spec2event.services.connector_spec_service import BRIDGE_SOURCE_MODES, FILE_LIKE_SOURCE_MODES


class ConnectorGeneratorService:
    def __init__(self) -> None:
        self.templates_root = get_settings().templates_root
        self.jinja = Environment(
            loader=FileSystemLoader(str(self.templates_root)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(
        self,
        run_id: str,
        canonical_model: dict[str, Any],
        source_summary: dict[str, Any],
    ) -> Path:
        settings = get_settings()
        workspace = settings.runs_root / run_id / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        context = self._build_context(canonical_model, source_summary)
        self._write(
            workspace / "pom.xml",
            self._render("integration-java-mdk/base/pom.xml.j2", context),
        )
        self._write(
            workspace / "Dockerfile",
            self._render("integration-java-mdk/base/Dockerfile.j2", context),
        )
        self._write(
            workspace / "README.md",
            self._render("integration-java-mdk/connector/README.md.j2", context),
        )
        self._write(
            workspace / "src/main/resources/application.yml",
            self._render("integration-java-mdk/connector/application.yml.j2", context),
        )
        self._write(
            workspace / "source-summary.json", json.dumps(source_summary, indent=2)
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/MicroIntegrationApplication.java",
            self._render(
                "integration-java-mdk/connector/MicroIntegrationApplication.java.j2", context
            ),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/api/SourceTriggerController.java",
            self._render(
                "integration-java-mdk/connector/SourceTriggerController.java.j2", context
            ),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java",
            self._render("integration-java-mdk/connector/CanonicalEventService.java.j2", context),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/service/SolacePublisherService.java",
            self._render("integration-java-mdk/base/SolacePublisherService.java.j2", context),
        )
        if context["file_mode"]:
            self._write(
                workspace
                / "src/main/java/com/spec2event/generated/service/SourcePollingService.java",
                self._render(
                    "integration-java-mdk/connector/SourcePollingService.java.j2", context
                ),
            )
        self._write(
            workspace / "src/test/java/com/spec2event/generated/CanonicalEventServiceTest.java",
            self._render(
                "integration-java-mdk/connector/CanonicalEventServiceTest.java.j2", context
            ),
        )
        self._write(
            workspace / "helm/Chart.yaml", self._render("helm/chart/Chart.yaml.j2", context)
        )
        self._write(
            workspace / "helm/values.yaml", self._render("helm/chart/values.yaml.j2", context)
        )
        self._write(
            workspace / "helm/templates/deployment.yaml",
            self._render("helm/chart/templates/deployment.yaml.j2", context),
        )
        self._write(
            workspace / "helm/templates/service.yaml",
            self._render("helm/chart/templates/service.yaml.j2", context),
        )
        self._write(
            workspace / "scripts/demo-curls.sh",
            self._render("integration-java-mdk/connector/demo-curls.sh.j2", context),
        )
        self._write(workspace / "ui/ui-metadata.json", json.dumps(context["ui_metadata"], indent=2))
        return workspace

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.jinja.get_template(template_name).render(**context)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _build_context(
        self, canonical_model: dict[str, Any], source_summary: dict[str, Any]
    ) -> dict[str, Any]:
        operations = []
        event_bindings = []
        for operation in canonical_model["operations"]:
            operation_events = []
            for candidate in operation.get("eventCandidates", []):
                binding_name = _camel(candidate["canonicalEventName"])
                operation_events.append({**candidate, "bindingName": binding_name})
                event_bindings.append(
                    {
                        "bindingName": binding_name,
                        "topicName": candidate["topicName"],
                        "eventName": candidate["canonicalEventName"],
                        "schemaName": candidate["schemaName"],
                        "applicationName": candidate["applicationName"],
                        "operationId": operation["operationId"],
                    }
                )
            operations.append(
                {
                    "operationId": operation["operationId"],
                    "method": operation["method"],
                    "path": operation["path"],
                    "summary": operation["summary"],
                    "eventCandidates": operation_events,
                }
            )

        unique_bindings = {item["bindingName"]: item for item in event_bindings}
        source_mode = canonical_model["sourceMode"]
        file_mode = source_mode in FILE_LIKE_SOURCE_MODES
        bridge_mode = source_mode in BRIDGE_SOURCE_MODES
        source_details = canonical_model.get("sourceDetails", {})

        return {
            "title": canonical_model["title"],
            "service_name": canonical_model["serviceName"],
            "service_version": canonical_model["serviceVersion"],
            "artifact_id": f"{canonical_model['serviceName']}-integration",
            "application_name": canonical_model["applicationNames"][0],
            "event_bindings": list(unique_bindings.values()),
            "operations": operations,
            "primary_operation": operations[0],
            "source_mode": source_mode,
            "adapter_type": canonical_model["adapterType"],
            "runtime_blueprint": canonical_model["runtimeBlueprint"],
            "bridge_mode": bridge_mode,
            "file_mode": file_mode,
            "webhook_mode": source_mode == "webhook",
            "public_ingress_path": canonical_model.get("publicIngressPath"),
            "internal_emit_path": canonical_model.get("internalEmitPath"),
            "internal_poll_path": canonical_model.get("internalPollPath"),
            "source_details": source_details,
            "runtime_env_entries": _runtime_env_entries(source_mode, source_details),
            "ui_metadata": {
                "serviceName": canonical_model["serviceName"],
                "title": canonical_model["title"],
                "topics": canonical_model["topics"],
                "schemaNames": canonical_model["schemaNames"],
                "applicationNames": canonical_model["applicationNames"],
                "sourceMode": source_mode,
                "adapterType": canonical_model["adapterType"],
                "runtimeBlueprint": canonical_model["runtimeBlueprint"],
                "operations": operations,
                "testFixtures": canonical_model["testFixtures"],
                "sourceDetails": source_details,
            },
            "canonical_model_json": json.dumps(canonical_model, indent=2),
            "source_summary_json": json.dumps(source_summary, indent=2),
        }


def _runtime_env_entries(source_mode: str, source_details: dict[str, Any]) -> list[dict[str, str]]:
    base = [
        {"name": "SOLACE_BROKER_URL", "default": ""},
        {"name": "SOLACE_VPN", "default": ""},
        {"name": "SOLACE_USERNAME", "default": ""},
        {"name": "SOLACE_PASSWORD", "default": ""},
    ]
    if source_mode == "webhook":
        return [
            *base,
            {"name": "WEBHOOK_SHARED_SECRET", "default": ""},
        ]
    if source_mode in FILE_LIKE_SOURCE_MODES:
        return [
            *base,
            {
                "name": "SOURCE_INPUT_DIRECTORY",
                "default": str(source_details.get("inputDirectory") or "./demo/inbox"),
            },
            {
                "name": "SOURCE_ARCHIVE_DIRECTORY",
                "default": str(source_details.get("archiveDirectory") or "./demo/archive"),
            },
            {
                "name": "SOURCE_POLL_INTERVAL_SECONDS",
                "default": str(source_details.get("pollIntervalSeconds") or "60"),
            },
            {
                "name": "SOURCE_MAX_FILES_PER_POLL",
                "default": str(source_details.get("maxFilesPerPoll") or "25"),
            },
        ]
    return [
        *base,
        {
            "name": "SOURCE_ADDRESS",
            "default": str(
                source_details.get("topic")
                or source_details.get("queueName")
                or source_details.get("stream")
                or ""
            ),
        },
        {
            "name": "SOURCE_CONSUMER_GROUP",
            "default": str(source_details.get("consumerGroup") or ""),
        },
        {
            "name": "SOURCE_CLIENT_ID",
            "default": str(source_details.get("clientId") or ""),
        },
    ]


def _camel(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value).split()
    if not cleaned:
        return "generatedBinding"
    head, *tail = cleaned
    return head[:1].lower() + head[1:] + "".join(part[:1].upper() + part[1:] for part in tail)


connector_generator_service = ConnectorGeneratorService()
