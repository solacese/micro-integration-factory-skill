from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from spec2event.config import get_settings


class DatabaseGeneratorService:
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
        discovery_summary: dict[str, Any],
    ) -> Path:
        settings = get_settings()
        workspace = settings.runs_root / run_id / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        context = self._build_context(canonical_model, discovery_summary)
        self._write(
            workspace / "pom.xml", self._render("integration-java-mdk/database/pom.xml.j2", context)
        )
        self._write(
            workspace / "Dockerfile",
            self._render("integration-java-mdk/base/Dockerfile.j2", context),
        )
        self._write(
            workspace / "README.md",
            self._render("integration-java-mdk/database/README.md.j2", context),
        )
        self._write(
            workspace / "src/main/resources/application.yml",
            self._render("integration-java-mdk/database/application.yml.j2", context),
        )
        self._write(
            workspace / "source-discovery.json", json.dumps(discovery_summary, indent=2)
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/MicroIntegrationApplication.java",
            self._render(
                "integration-java-mdk/database/MicroIntegrationApplication.java.j2", context
            ),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/api/DatabasePollingController.java",
            self._render(
                "integration-java-mdk/database/DatabasePollingController.java.j2", context
            ),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java",
            self._render("integration-java-mdk/database/CanonicalEventService.java.j2", context),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/service/DatabasePollingService.java",
            self._render(
                "integration-java-mdk/database/DatabasePollingService.java.j2", context
            ),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/service/SolacePublisherService.java",
            self._render("integration-java-mdk/base/SolacePublisherService.java.j2", context),
        )
        self._write(
            workspace / "src/test/java/com/spec2event/generated/CanonicalEventServiceTest.java",
            self._render(
                "integration-java-mdk/database/CanonicalEventServiceTest.java.j2", context
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
            self._render("integration-java-mdk/database/demo-curls.sh.j2", context),
        )
        self._write(workspace / "ui/ui-metadata.json", json.dumps(context["ui_metadata"], indent=2))
        return workspace

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.jinja.get_template(template_name).render(**context)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _build_context(
        self, canonical_model: dict[str, Any], discovery_summary: dict[str, Any]
    ) -> dict[str, Any]:
        operation = canonical_model["operations"][0]
        event_bindings = []
        for candidate in operation.get("eventCandidates", []):
            event_bindings.append(
                {
                    **candidate,
                    "bindingName": _camel(candidate["canonicalEventName"]),
                    "eventName": candidate["canonicalEventName"],
                    "operationId": operation["operationId"],
                }
            )
        columns = discovery_summary["columns"]
        return {
            "title": canonical_model["title"],
            "service_name": canonical_model["serviceName"],
            "service_version": canonical_model["serviceVersion"],
            "artifact_id": f"{canonical_model['serviceName']}-integration",
            "application_name": canonical_model["applicationNames"][0],
            "event_bindings": event_bindings,
            "database_operation": {
                "operationId": operation["operationId"],
                "summary": operation["summary"],
                "tableName": discovery_summary["selectedTable"],
                "qualifiedTableName": discovery_summary["selectedTableQualifiedName"],
            },
            "database_config": canonical_model["databaseConfig"],
            "database_columns": columns,
            "runtime_env_entries": [
                {"name": "SOLACE_BROKER_URL", "default": ""},
                {"name": "SOLACE_VPN", "default": ""},
                {"name": "SOLACE_USERNAME", "default": ""},
                {"name": "SOLACE_PASSWORD", "default": ""},
                {"name": "SOURCE_DATABASE_HOST", "default": ""},
                {"name": "SOURCE_DATABASE_PORT", "default": "5432"},
                {"name": "SOURCE_DATABASE_NAME", "default": ""},
                {"name": "SOURCE_DATABASE_USERNAME", "default": ""},
                {"name": "SOURCE_DATABASE_PASSWORD", "default": ""},
                {"name": "SOURCE_DATABASE_SSLMODE", "default": "require"},
                {"name": "SOURCE_DATABASE_POLL_INTERVAL_SECONDS", "default": "60"},
                {"name": "SOURCE_DATABASE_INITIAL_DELAY_SECONDS", "default": "300"},
                {"name": "SOURCE_DATABASE_FETCH_SIZE", "default": "50"},
            ],
            "ui_metadata": {
                "serviceName": canonical_model["serviceName"],
                "title": canonical_model["title"],
                "topics": canonical_model["topics"],
                "schemaNames": canonical_model["schemaNames"],
                "applicationNames": canonical_model["applicationNames"],
                "sourceMode": "database",
                "headerContract": canonical_model.get("headerContract"),
                "compatibilityPolicy": canonical_model.get("compatibilityPolicy"),
                "databaseSummary": discovery_summary,
                "testFixtures": canonical_model["testFixtures"],
            },
            "header_contract": canonical_model.get("headerContract", {}),
            "compatibility_policy": canonical_model.get("compatibilityPolicy"),
            "canonical_model_json": json.dumps(canonical_model, indent=2),
            "source_summary_json": json.dumps(discovery_summary, indent=2),
        }


def _camel(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value).split()
    if not cleaned:
        return "generatedBinding"
    head, *tail = cleaned
    return head[:1].lower() + head[1:] + "".join(part[:1].upper() + part[1:] for part in tail)


database_generator_service = DatabaseGeneratorService()
