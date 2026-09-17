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
        source_summary: dict[str, Any],
        raw_spec: str,
    ) -> Path:
        settings = get_settings()
        workspace = settings.runs_root / run_id / "workspace"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True, exist_ok=True)

        context = self._build_context(canonical_model, source_summary)
        ingress_type = canonical_model.get("ingressType", "rest_controller")

        # -- Core Solace MDK files (always generated) --
        self._write(
            workspace / "pom.xml", self._render("integration-java-mdk/base/pom.xml.j2", context)
        )
        self._write(
            workspace / "Dockerfile",
            self._render("integration-java-mdk/base/Dockerfile.j2", context),
        )
        self._write(
            workspace / ".dockerignore",
            self._render("integration-java-mdk/base/dockerignore.j2", context),
        )
        self._write(
            workspace / ".env.example",
            self._render("integration-java-mdk/base/env.example.j2", context),
        )
        self._write(
            workspace / "README.md", self._render("integration-java-mdk/base/README.md.j2", context)
        )
        self._write(
            workspace / "docs/micro-integration.md",
            self._render("integration-java-mdk/base/micro-integration.md.j2", context),
        )
        self._write(
            workspace / "docs/event-portal-schema.md",
            self._render("integration-java-mdk/base/event-portal-schema.md.j2", context),
        )
        self._write(
            workspace / "docs/operations.md",
            self._render("integration-java-mdk/base/operations.md.j2", context),
        )
        self._write(
            workspace / "event-portal/event-api.json",
            self._render("integration-java-mdk/base/event-api.json.j2", context),
        )
        self._write(
            workspace / "src/main/resources/application.yml",
            self._render("integration-java-mdk/base/application.yml.j2", context),
        )
        self._write(workspace / "src/main/resources/source-spec.txt", raw_spec)
        self._write(
            workspace / "src/main/java/com/spec2event/generated/MicroIntegrationApplication.java",
            self._render("integration-java-mdk/base/MicroIntegrationApplication.java.j2", context),
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
            workspace / "helm/templates/pdb.yaml",
            self._render("helm/chart/templates/pdb.yaml.j2", context),
        )
        self._write(
            workspace / "scripts/demo-curls.sh",
            self._render("integration-java-mdk/base/demo-curls.sh.j2", context),
        )
        self._write(workspace / "ui/ui-metadata.json", json.dumps(context["ui_metadata"], indent=2))
        self._write_vscode_files(workspace, context)

        # -- MDK binding capabilities factories (always generated) --
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/binding"
            / "SourceConsumerBindingCapabilitiesFactory.java",
            self._render(
                "integration-java-mdk/base/SourceConsumerBindingCapabilitiesFactory.java.j2",
                context,
            ),
        )
        self._write(
            workspace
            / "src/main/java/com/spec2event/generated/binding"
            / "SourceProducerBindingCapabilitiesFactory.java",
            self._render(
                "integration-java-mdk/base/SourceProducerBindingCapabilitiesFactory.java.j2",
                context,
            ),
        )

        # -- Runtime config overlay (maps workflows to Solace destinations) --
        self._write(
            workspace / "config/application-runtime.yml",
            self._render("integration-java-mdk/base/application-runtime.yml.j2", context),
        )

        # -- Ingress adapter (varies by source type) --
        if ingress_type == "rest_controller":
            self._write(
                workspace
                / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java",
                self._render(
                    "integration-java-mdk/base/GeneratedApiController.java.j2", context
                ),
            )
            if context.get("stripe_enabled"):
                self._write(
                    workspace
                    / "src/main/java/com/spec2event/generated/api/StripeWebhookController.java",
                    self._render(
                        "integration-java-mdk/base/StripeWebhookController.java.j2", context
                    ),
                )
                self._write(
                    workspace
                    / "src/main/java/com/spec2event/generated/service/StripeSignatureVerifier.java",
                    self._render(
                        "integration-java-mdk/base/StripeSignatureVerifier.java.j2", context
                    ),
                )
        elif ingress_type == "polling_consumer":
            self._write(
                workspace
                / "src/main/java/com/spec2event/generated/service/PollingConsumerService.java",
                self._render(
                    "integration-java-mdk/base/PollingConsumerService.java.j2", context
                ),
            )
        elif ingress_type == "event_subscriber":
            self._write(
                workspace
                / "src/main/java/com/spec2event/generated/service/EventSubscriberService.java",
                self._render(
                    "integration-java-mdk/base/EventSubscriberService.java.j2", context
                ),
            )

        return workspace

    def _render(self, template_name: str, context: dict[str, Any]) -> str:
        return self.jinja.get_template(template_name).render(**context)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_vscode_files(self, workspace: Path, context: dict[str, Any]) -> None:
        service_name = context["service_name"]
        self._write(
            workspace / f"{service_name}.code-workspace",
            json.dumps(
                {
                    "folders": [{"path": "."}],
                    "settings": {
                        "java.configuration.updateBuildConfiguration": "automatic",
                        "java.compile.nullAnalysis.mode": "automatic",
                        "files.exclude": {"target": True},
                    },
                    "extensions": {
                        "recommendations": [
                            "vscjava.vscode-java-pack",
                            "vmware.vscode-spring-boot",
                            "redhat.vscode-yaml",
                        ]
                    },
                },
                indent=2,
            ),
        )
        self._write(
            workspace / ".vscode/settings.json",
            json.dumps(
                {
                    "java.configuration.updateBuildConfiguration": "automatic",
                    "java.compile.nullAnalysis.mode": "automatic",
                    "files.exclude": {"target": True},
                },
                indent=2,
            ),
        )
        self._write(
            workspace / ".vscode/extensions.json",
            json.dumps(
                {
                    "recommendations": [
                        "vscjava.vscode-java-pack",
                        "vmware.vscode-spring-boot",
                        "redhat.vscode-yaml",
                    ]
                },
                indent=2,
            ),
        )
        self._write(
            workspace / ".vscode/launch.json",
            json.dumps(
                {
                    "version": "0.2.0",
                    "configurations": [
                        {
                            "type": "java",
                            "name": "Run Micro Integration",
                            "request": "launch",
                            "mainClass": "com.spec2event.generated.MicroIntegrationApplication",
                            "projectName": context["artifact_id"],
                            "envFile": "${workspaceFolder}/.env",
                        }
                    ],
                },
                indent=2,
            ),
        )

    def _build_context(
        self, canonical_model: dict[str, Any], source_summary: dict[str, Any]
    ) -> dict[str, Any]:
        event_bindings = []
        for operation in canonical_model["operations"]:
            for candidate in operation.get("eventCandidates", []):
                binding_name = _camel(candidate["canonicalEventName"])
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
                    "eventCandidates": [
                        {**candidate, "bindingName": _camel(candidate["canonicalEventName"])}
                        for candidate in operation.get("eventCandidates", [])
                    ],
                    "emitsEvent": operation["emitsEvent"],
                }
            )
        ingress_type = canonical_model.get("ingressType", "rest_controller")
        source_binder_type = _source_binder_type(ingress_type)
        builder_draft = canonical_model.get("builderDraft")
        if not isinstance(builder_draft, dict):
            builder_draft = {}

        workflows = []
        for index, binding in enumerate(unique_bindings.values()):
            workflows.append(
                {
                    "index": index,
                    "input_binder": source_binder_type,
                    "input_destination": binding["topicName"],
                    "output_binder": "solace",
                    "output_destination": binding["topicName"],
                }
            )

        sample_payload = {}
        test_fixtures = canonical_model.get("testFixtures")
        if isinstance(test_fixtures, list) and test_fixtures:
            first_fixture = test_fixtures[0]
            if isinstance(first_fixture, dict) and isinstance(first_fixture.get("payload"), dict):
                sample_payload = first_fixture["payload"]

        event_portal_model = {
            "name": canonical_model["title"],
            "version": canonical_model["serviceVersion"],
            "application": f"{canonical_model['serviceName']}-integration",
            "schemaSource": "Micro Integration Factory generated from captured payload",
            "channels": [
                {
                    "topic": binding["topicName"],
                    "direction": "publish",
                    "eventName": binding["eventName"],
                    "schemaName": binding["schemaName"],
                    "applicationName": binding["applicationName"],
                }
                for binding in unique_bindings.values()
            ],
            "schemas": [
                {
                    "name": schema_name,
                    "contentType": "application/json",
                    "schema": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": (
                            "Replace with the approved Event Portal schema when available."
                        ),
                    },
                }
                for schema_name in canonical_model["schemaNames"]
            ],
            "builderDraft": builder_draft,
        }

        return {
            "title": canonical_model["title"],
            "service_name": canonical_model["serviceName"],
            "service_version": canonical_model["serviceVersion"],
            "artifact_id": f"{canonical_model['serviceName']}-integration",
            "application_name": f"{canonical_model['serviceName']}-integration",
            "event_bindings": list(unique_bindings.values()),
            "operations": operations,
            "workflows": workflows,
            "source_binder_type": source_binder_type,
            "ingress_type": ingress_type,
            "stripe_enabled": canonical_model["stripeEnabled"],
            "transform_language": canonical_model.get("transformLanguage", "java_sdk"),
            "ui_metadata": {
                "serviceName": canonical_model["serviceName"],
                "title": canonical_model["title"],
                "operations": operations,
                "testFixtures": canonical_model.get("testFixtures", []),
                "topics": canonical_model["topics"],
                "schemaNames": canonical_model["schemaNames"],
                "applicationNames": canonical_model["applicationNames"],
            },
            "canonical_model_json": json.dumps(canonical_model, indent=2),
            "source_summary_json": json.dumps(source_summary, indent=2),
            "builder_draft_json": json.dumps(builder_draft, indent=2),
            "sample_payload_json": json.dumps(sample_payload, indent=2),
            "event_portal_model_json": json.dumps(event_portal_model, indent=2),
        }


def _source_binder_type(ingress_type: str) -> str:
    """Map ingress type to the Spring Cloud Stream binder type name."""
    return {
        "rest_controller": "solace",
        "polling_consumer": "polling",
        "event_subscriber": "external",
    }.get(ingress_type, "solace")


def _camel(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value).split()
    if not cleaned:
        return "generatedBinding"
    head, *tail = cleaned
    return head[:1].lower() + head[1:] + "".join(part[:1].upper() + part[1:] for part in tail)


generator_service = GeneratorService()
