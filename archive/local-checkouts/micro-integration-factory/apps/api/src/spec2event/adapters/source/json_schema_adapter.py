from __future__ import annotations

import json
import re
from typing import Any

from spec2event.adapters.source.base import (
    SourceAdapter,
    SourceCanonicalResult,
    SourceParseResult,
    SourceSummary,
)


def _safe_slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "generated-service"


def _pascal(text: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _example_from_schema(schema: dict[str, Any] | None, depth: int = 0) -> Any:
    if not schema or depth > 4:
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "object" or schema.get("properties"):
        properties = schema.get("properties") or {}
        return {key: _example_from_schema(value, depth + 1) for key, value in properties.items()}
    if schema_type == "array":
        item_example = _example_from_schema(schema.get("items"), depth + 1)
        return [] if item_example is None else [item_example]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return schema.get("title") or "string"
    return None


def _singularize(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def _entities_from_schema(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract entity definitions from a JSON Schema.

    Handles three shapes:
    - Top-level object with ``title`` — single entity.
    - ``definitions`` / ``$defs`` containing multiple named objects.
    - Both (primary entity + supporting definitions).
    """
    entities: list[dict[str, Any]] = []
    definitions = doc.get("definitions", doc.get("$defs", {}))
    if doc.get("type") == "object" or doc.get("properties"):
        entities.append({"name": doc.get("title", "Resource"), "schema": doc})
    for name, defn in definitions.items():
        if isinstance(defn, dict) and (defn.get("type") == "object" or defn.get("properties")):
            entities.append({"name": defn.get("title", name), "schema": defn})
    if not entities:
        entities.append({"name": doc.get("title", "Resource"), "schema": doc})
    return entities


class JsonSchemaSourceAdapter(SourceAdapter):
    source_type = "json_schema"
    accepted_extensions = [".json", ".schema.json"]
    accepted_content_types = ["application/json", "application/schema+json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("JSON Schema input must be a JSON object")
        if not any(key in doc for key in ("type", "properties", "$schema", "definitions", "$defs")):
            raise ValueError("Not a valid JSON Schema document")
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        title = document.get("title", "Generated Service")
        service_name = _safe_slug(title)
        properties = document.get("properties", {})
        definitions = document.get("definitions", document.get("$defs", {}))
        entities = _entities_from_schema(document)
        return SourceSummary(
            service_name=service_name,
            summary={
                "title": title,
                "serviceName": service_name,
                "version": "1.0.0",
                "propertyCount": len(properties),
                "definitionCount": len(definitions),
                "entityCount": len(entities),
                "operationCount": len(entities) * 3,
            },
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        title = document.get("title", "Generated Service")
        service_name = _safe_slug(title)
        application_name = f"{service_name}-integration"
        entities = _entities_from_schema(document)

        operations: list[dict[str, Any]] = []
        topics: set[str] = set()
        schema_names: set[str] = set()
        test_fixtures: list[dict[str, Any]] = []

        for entity_info in entities:
            entity_title = entity_info["name"]
            entity_schema = entity_info["schema"]
            entity_slug = _safe_slug(_singularize(entity_title))
            entity_pascal = _pascal(entity_slug)

            for action, method in [("created", "POST"), ("updated", "PUT"), ("deleted", "DELETE")]:
                op_id = f"{action}{entity_pascal}"
                topic = f"{service_name}/{entity_slug}/{action}/v1"
                event_name = f"{entity_pascal}{_pascal(action)}"
                schema_name = f"{event_name}Payload"
                topics.add(topic)
                schema_names.add(schema_name)

                path = f"/{entity_slug}" if method == "POST" else f"/{entity_slug}/{{id}}"
                expects_body = method in ("POST", "PUT")
                request_schema = entity_schema if expects_body else None
                request_schema_name = f"{entity_pascal}Request" if expects_body else None
                response_schema_name = f"{entity_pascal}Response"
                if request_schema_name:
                    schema_names.add(request_schema_name)
                schema_names.add(response_schema_name)

                event_candidate = {
                    "operationId": op_id,
                    "canonicalEventName": event_name,
                    "topicName": topic,
                    "schemaName": schema_name,
                    "applicationName": application_name,
                    "emitsEvent": True,
                }

                operations.append(
                    {
                        "operationId": op_id,
                        "method": method,
                        "path": path,
                        "summary": f"{action.capitalize()} {entity_title}",
                        "tags": [entity_slug],
                        "requestSchemaName": request_schema_name,
                        "responseSchemaName": response_schema_name,
                        "requestSchema": request_schema,
                        "responseSchema": entity_schema,
                        "emitsEvent": True,
                        "eventCandidates": [event_candidate],
                    }
                )

                if expects_body:
                    test_fixtures.append(
                        {
                            "operationId": op_id,
                            "label": f"{method} /{entity_slug}",
                            "method": method,
                            "path": path.replace("{id}", "1"),
                            "payload": _example_from_schema(entity_schema),
                        }
                    )

        return SourceCanonicalResult(
            canonical_model={
                "title": title,
                "serviceName": service_name,
                "serviceVersion": "1.0.0",
                "servers": [],
                "authSchemes": [],
                "operations": operations,
                "topics": sorted(topics),
                "schemaNames": sorted(schema_names),
                "applicationNames": sorted({application_name}),
                "stripeEnabled": False,
                "testFixtures": test_fixtures,
                "ingressType": "rest_controller",
            }
        )
