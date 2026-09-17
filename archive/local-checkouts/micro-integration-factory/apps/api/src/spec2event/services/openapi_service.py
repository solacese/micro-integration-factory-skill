from __future__ import annotations

import json
import re
from typing import Any

import jsonref
import yaml
from openapi_spec_validator import validate


def _safe_slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "generated-service"


def _pascal(text: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def _singularize(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def _schema_name(schema: dict[str, Any] | None, fallback: str) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref")
    if ref and "/" in ref:
        return ref.rsplit("/", 1)[-1]
    title = schema.get("title")
    if title:
        return _pascal(title)
    return _pascal(fallback)


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
        return {
            key: _example_from_schema(value, depth + 1)
            for key, value in properties.items()
        }
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
        format_hint = schema.get("format")
        if format_hint == "date-time":
            return "2026-01-01T00:00:00Z"
        if format_hint == "date":
            return "2026-01-01"
        if format_hint == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return schema.get("title") or "string"
    if "oneOf" in schema and schema["oneOf"]:
        return _example_from_schema(schema["oneOf"][0], depth + 1)
    if "anyOf" in schema and schema["anyOf"]:
        return _example_from_schema(schema["anyOf"][0], depth + 1)
    return None


def _parameter_example(parameter: dict[str, Any]) -> str:
    example = _example_from_schema(parameter.get("schema"))
    if example is None:
        example = parameter.get("example")
    if example is None:
        example = parameter.get("name") or "value"
    return str(example)


def _fixture_path(path: str, parameters: list[dict[str, Any]]) -> str:
    resolved = path
    for parameter in parameters:
        if parameter.get("in") != "path":
            continue
        name = parameter.get("name")
        if not name:
            continue
        resolved = resolved.replace(f"{{{name}}}", _parameter_example(parameter))
    return resolved


def load_openapi_document(raw_content: str) -> dict[str, Any]:
    if raw_content.lstrip().startswith("{"):
        doc = json.loads(raw_content)
    else:
        doc = yaml.safe_load(raw_content)
    resolved = jsonref.replace_refs(doc, lazy_load=False, proxies=False)
    validate(resolved)
    return resolved


def _extract_schema(content: dict[str, Any] | None) -> dict[str, Any] | None:
    if not content:
        return None
    for media_type in (
        "application/json",
        "application/x-www-form-urlencoded",
        "multipart/form-data",
    ):
        media = content.get(media_type)
        if media and media.get("schema"):
            return media["schema"]
    first = next(iter(content.values()), None)
    if first:
        return first.get("schema")
    return None


def _infer_domain(tags: list[str], path_segments: list[str], service_name: str) -> str:
    if tags:
        return _safe_slug(tags[0])
    if path_segments:
        return _safe_slug(path_segments[0])
    return service_name


def _infer_source(path: str, tags: list[str], service_name: str) -> str:
    joined = " ".join([path, *tags, service_name]).lower()
    if "stripe" in joined:
        return "stripe"
    return service_name


def _infer_entity(path_segments: list[str], service_name: str) -> str:
    concrete = [segment for segment in path_segments if not segment.startswith("{")]
    if concrete:
        return _safe_slug(_singularize(concrete[-1]))
    return service_name


def _infer_action(method: str, operation_id: str, summary: str, source: str, entity: str) -> str:
    text = f"{operation_id} {summary}".lower()
    if source == "stripe" and "refund" in text:
        return "refunded"
    if "success" in text or "succeeded" in text:
        return "succeeded"
    if "fail" in text:
        return "failed"
    if "update" in text or method.lower() == "patch":
        return "updated"
    if method.lower() == "post":
        return "created"
    if method.lower() == "put":
        return "replaced"
    if method.lower() == "delete":
        return "deleted"
    return "observed"


def _emit_business_event(method: str, tags: list[str], path: str) -> bool:
    lowered = " ".join(tags + [path]).lower()
    return method.lower() in {"post", "put", "patch"} or "webhook" in lowered


def _stripe_event_candidates(
    domain: str, source: str, application_name: str
) -> list[dict[str, str]]:
    return [
        {
            "canonicalEventName": "StripePaymentIntentSucceeded",
            "topicName": f"{domain}/{source}/payment_intent/succeeded/v1",
            "schemaName": "StripePaymentIntentSucceededPayload",
            "applicationName": application_name,
        },
        {
            "canonicalEventName": "StripePaymentIntentFailed",
            "topicName": f"{domain}/{source}/payment_intent/failed/v1",
            "schemaName": "StripePaymentIntentFailedPayload",
            "applicationName": application_name,
        },
        {
            "canonicalEventName": "StripeChargeRefunded",
            "topicName": f"{domain}/{source}/charge/refunded/v1",
            "schemaName": "StripeChargeRefundedPayload",
            "applicationName": application_name,
        },
    ]


def summarize_openapi(doc: dict[str, Any]) -> dict[str, Any]:
    info = doc.get("info", {})
    title = info.get("title", "Generated Service")
    version = info.get("version", "1.0.0")
    servers = [server.get("url", "") for server in doc.get("servers", [])]
    operations = []

    for path, path_item in doc.get("paths", {}).items():
        for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
            if method not in path_item:
                continue
            operation = path_item[method]
            operations.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operationId": operation.get("operationId") or _safe_slug(f"{method}-{path}"),
                    "summary": operation.get("summary") or operation.get("description") or "",
                    "tags": operation.get("tags", []),
                }
            )

    return {
        "title": title,
        "version": version,
        "serviceName": _safe_slug(title),
        "servers": servers,
        "operationCount": len(operations),
        "operations": operations,
    }


def canonicalize_openapi(doc: dict[str, Any]) -> dict[str, Any]:
    info = doc.get("info", {})
    title = info.get("title", "Generated Service")
    service_name = _safe_slug(title)
    service_version = info.get("version", "1.0.0")
    auth_schemes = list((doc.get("components", {}).get("securitySchemes") or {}).keys())
    operations = []
    topics: set[str] = set()
    schema_names: set[str] = set()
    application_names: set[str] = set()
    stripe_enabled = False
    test_fixtures: list[dict[str, Any]] = []

    for path, path_item in doc.get("paths", {}).items():
        path_segments = [segment for segment in path.strip("/").split("/") if segment]
        for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
            if method not in path_item:
                continue
            operation = path_item[method]
            parameters = [
                *(path_item.get("parameters") or []),
                *(operation.get("parameters") or []),
            ]
            operation_id = operation.get("operationId") or _safe_slug(f"{method}-{path}")
            summary = operation.get("summary") or operation.get("description") or operation_id
            tags = operation.get("tags", [])
            request_schema = _extract_schema((operation.get("requestBody") or {}).get("content"))
            responses = operation.get("responses", {})
            response_schema = None
            for code, response in responses.items():
                if str(code).startswith("2"):
                    response_schema = _extract_schema((response or {}).get("content"))
                    if response_schema:
                        break

            domain = _infer_domain(tags, path_segments, service_name)
            source = _infer_source(path, tags, service_name)
            entity = _infer_entity(path_segments, service_name)
            action = _infer_action(method, operation_id, summary, source, entity)
            emits_event = _emit_business_event(method, tags, path)
            application_name = f"{service_name}-integration"

            event_candidates: list[dict[str, Any]] = []
            if "stripe" in source or "stripe" in path.lower():
                stripe_enabled = True
                event_candidates = [
                    {**candidate, "operationId": operation_id, "emitsEvent": True}
                    for candidate in _stripe_event_candidates(
                        domain or "payments",
                        "stripe",
                        application_name,
                    )
                ]
            elif emits_event:
                canonical_event_name = _pascal(f"{source} {entity} {action}")
                topic_name = f"{domain}/{source}/{entity}/{action}/v1"
                schema_name = f"{canonical_event_name}Payload"
                event_candidates = [
                    {
                        "operationId": operation_id,
                        "canonicalEventName": canonical_event_name,
                        "topicName": topic_name,
                        "schemaName": schema_name,
                        "applicationName": application_name,
                        "emitsEvent": True,
                    }
                ]

            for event_candidate in event_candidates:
                topics.add(event_candidate["topicName"])
                schema_names.add(event_candidate["schemaName"])
                application_names.add(event_candidate["applicationName"])

            request_schema_name = _schema_name(request_schema, f"{operation_id}Request")
            response_schema_name = _schema_name(response_schema, f"{operation_id}Response")
            if request_schema_name:
                schema_names.add(request_schema_name)
            if response_schema_name:
                schema_names.add(response_schema_name)

            operations.append(
                {
                    "operationId": operation_id,
                    "method": method.upper(),
                    "path": path,
                    "summary": summary,
                    "tags": tags,
                    "requestSchemaName": request_schema_name,
                    "responseSchemaName": response_schema_name,
                    "requestSchema": request_schema,
                    "responseSchema": response_schema,
                    "emitsEvent": emits_event,
                    "eventCandidates": event_candidates,
                }
            )
            if emits_event:
                test_fixtures.append(
                    {
                        "operationId": operation_id,
                        "label": f"{method.upper()} {path}",
                        "method": method.upper(),
                        "path": _fixture_path(path, parameters),
                        "payload": _example_from_schema(request_schema),
                    }
                )

    return {
        "title": title,
        "serviceName": service_name,
        "serviceVersion": service_version,
        "servers": [server.get("url", "") for server in doc.get("servers", [])],
        "authSchemes": auth_schemes,
        "operations": operations,
        "topics": sorted(topics),
        "schemaNames": sorted(schema_names),
        "applicationNames": sorted(application_names or {f"{service_name}-integration"}),
        "stripeEnabled": stripe_enabled,
        "testFixtures": test_fixtures,
    }
