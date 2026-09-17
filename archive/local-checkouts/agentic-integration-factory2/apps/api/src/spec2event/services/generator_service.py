from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from spec2event.config import get_settings


class GeneratorService:
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
        openapi_summary: dict[str, Any],
        raw_spec: str,
    ) -> Path:
        settings = get_settings()
        workspace = settings.runs_root / run_id / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        context = self._build_context(canonical_model, openapi_summary)
        self._write(
            workspace / "pom.xml", self._render("integration-java-mdk/base/pom.xml.j2", context)
        )
        self._write(
            workspace / "Dockerfile",
            self._render("integration-java-mdk/base/Dockerfile.j2", context),
        )
        self._write(
            workspace / "README.md", self._render("integration-java-mdk/base/README.md.j2", context)
        )
        self._write(
            workspace / "src/main/resources/application.yml",
            self._render("integration-java-mdk/base/application.yml.j2", context),
        )
        self._write(workspace / "src/main/resources/openapi-source.yaml", raw_spec)
        self._write(
            workspace / "src/main/java/com/spec2event/generated/MicroIntegrationApplication.java",
            self._render("integration-java-mdk/base/MicroIntegrationApplication.java.j2", context),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java",
            self._render("integration-java-mdk/base/GeneratedApiController.java.j2", context),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/api/StripeWebhookController.java",
            self._render("integration-java-mdk/base/StripeWebhookController.java.j2", context),
        )
        self._write(
            workspace / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java",
            self._render("integration-java-mdk/base/CanonicalEventService.java.j2", context),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/service/SolacePublisherService.java",
            self._render("integration-java-mdk/base/SolacePublisherService.java.j2", context),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/service/StripeSignatureVerifier.java",
            self._render("integration-java-mdk/base/StripeSignatureVerifier.java.j2", context),
        )
        self._write(
            workspace / "src/test/java/com/spec2event/generated/CanonicalEventServiceTest.java",
            self._render("integration-java-mdk/base/CanonicalEventServiceTest.java.j2", context),
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
            self._render("integration-java-mdk/base/demo-curls.sh.j2", context),
        )
        self._write(workspace / "ui/ui-metadata.json", json.dumps(context["ui_metadata"], indent=2))
        return workspace

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.jinja.get_template(template_name).render(**context)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _build_context(
        self, canonical_model: dict[str, Any], openapi_summary: dict[str, Any]
    ) -> dict[str, Any]:
        event_bindings = []
        for operation in canonical_model["operations"]:
            for candidate in operation.get("eventCandidates", []):
                binding_name = _camel(candidate["canonicalEventName"])
                event_bindings.append(
                    {
                        **candidate,
                        "bindingName": binding_name,
                        "eventName": candidate["canonicalEventName"],
                        "operationId": operation["operationId"],
                    }
                )
        unique_bindings = {item["bindingName"]: item for item in event_bindings}
        operations = []
        for operation in canonical_model["operations"]:
            path_params = [
                segment.strip("{}")
                for segment in operation["path"].split("/")
                if segment.startswith("{")
            ]
            method_name = _camel(f"{operation['method'].lower()}_{operation['operationId']}")
            operations.append(
                {
                    "operationId": operation["operationId"],
                    "method": operation["method"],
                    "path": operation["path"],
                    "summary": operation.get("summary") or operation["operationId"],
                    "methodName": method_name,
                    "expectsBody": bool(operation.get("requestSchema")),
                    "pathParams": path_params,
                    "renderInGeneratedController": not operation.get("stripeWebhook", False),
                    "stripeWebhook": bool(operation.get("stripeWebhook", False)),
                    "eventCandidates": [
                        {**candidate, "bindingName": _camel(candidate["canonicalEventName"])}
                        for candidate in operation.get("eventCandidates", [])
                    ],
                    "emitsEvent": operation["emitsEvent"],
                }
            )
        return {
            "title": canonical_model["title"],
            "service_name": canonical_model["serviceName"],
            "service_version": canonical_model["serviceVersion"],
            "artifact_id": f"{canonical_model['serviceName']}-integration",
            "application_name": f"{canonical_model['serviceName']}-integration",
            "event_bindings": list(unique_bindings.values()),
            "operations": operations,
            "stripe_enabled": canonical_model["stripeEnabled"],
            "ui_metadata": {
                "serviceName": canonical_model["serviceName"],
                "title": canonical_model["title"],
                "operations": operations,
                "testFixtures": canonical_model.get("testFixtures", []),
                "topics": canonical_model["topics"],
                "schemaNames": canonical_model["schemaNames"],
                "applicationNames": canonical_model["applicationNames"],
                "sourceMode": canonical_model.get("sourceMode", "openapi"),
                "headerContract": canonical_model.get("headerContract"),
                "compatibilityPolicy": canonical_model.get("compatibilityPolicy"),
            },
            "runtime_env_entries": [
                {"name": "SOLACE_BROKER_URL", "default": ""},
                {"name": "SOLACE_VPN", "default": ""},
                {"name": "SOLACE_USERNAME", "default": ""},
                {"name": "SOLACE_PASSWORD", "default": ""},
                *(
                    [{"name": "STRIPE_WEBHOOK_SECRET", "default": ""}]
                    if canonical_model["stripeEnabled"]
                    else []
                ),
            ],
            "header_contract": canonical_model.get("headerContract", {}),
            "compatibility_policy": canonical_model.get("compatibilityPolicy"),
            "canonical_model_json": json.dumps(canonical_model, indent=2),
            "openapi_summary_json": json.dumps(openapi_summary, indent=2),
        }


def _camel(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value).split()
    if not cleaned:
        return "generatedBinding"
    head, *tail = cleaned
    return head[:1].lower() + head[1:] + "".join(part[:1].upper() + part[1:] for part in tail)


generator_service = GeneratorService()
