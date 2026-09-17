from __future__ import annotations

import json
import re
from typing import Any

import jsonref
import yaml
from openapi_spec_validator import validate

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_SCHEMA_FORMAT = "json-schema"
DEFAULT_SERDE_FAMILY = "jackson-json"
DEFAULT_COMPATIBILITY_MODE = "backward_additive"
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_SCHEMA_VERSIONING_POLICY = "topic-major-schema-additive"
DEFAULT_REGISTRY_COORDINATES = "event-portal-only"
DEFAULT_REQUIRED_HEADERS = [
    "content-type",
    "event-type",
    "schema-name",
    "schema-version",
    "source-system",
    "source-record-id",
    "correlation-id",
    "occurred-at",
]

STRIPE_EVENT_CATALOG: list[tuple[str, str, str]] = [
    ("payment_intent.succeeded", "StripePaymentIntentSucceeded", "payment_intent/succeeded"),
    ("payment_intent.payment_failed", "StripePaymentIntentFailed", "payment_intent/failed"),
    ("payment_intent.created", "StripePaymentIntentCreated", "payment_intent/created"),
    ("payment_intent.processing", "StripePaymentIntentProcessing", "payment_intent/processing"),
    ("payment_intent.canceled", "StripePaymentIntentCanceled", "payment_intent/canceled"),
    ("charge.succeeded", "StripeChargeSucceeded", "charge/succeeded"),
    ("charge.failed", "StripeChargeFailed", "charge/failed"),
    ("charge.refunded", "StripeChargeRefunded", "charge/refunded"),
    ("refund.created", "StripeRefundCreated", "refund/created"),
    ("refund.updated", "StripeRefundUpdated", "refund/updated"),
    ("refund.failed", "StripeRefundFailed", "refund/failed"),
    ("invoice.created", "StripeInvoiceCreated", "invoice/created"),
    ("invoice.paid", "StripeInvoicePaid", "invoice/paid"),
    ("invoice.payment_failed", "StripeInvoicePaymentFailed", "invoice/payment_failed"),
    (
        "checkout.session.completed",
        "StripeCheckoutSessionCompleted",
        "checkout_session/completed",
    ),
    (
        "checkout.session.expired",
        "StripeCheckoutSessionExpired",
        "checkout_session/expired",
    ),
    (
        "checkout.session.async_payment_succeeded",
        "StripeCheckoutSessionAsyncPaymentSucceeded",
        "checkout_session/async_payment_succeeded",
    ),
    ("dispute.created", "StripeDisputeCreated", "dispute/created"),
    ("dispute.updated", "StripeDisputeUpdated", "dispute/updated"),
    ("dispute.closed", "StripeDisputeClosed", "dispute/closed"),
]


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


def _header_contract() -> dict[str, Any]:
    return {
        "contentType": DEFAULT_CONTENT_TYPE,
        "requiredHeaders": list(DEFAULT_REQUIRED_HEADERS),
        "schemaFormat": DEFAULT_SCHEMA_FORMAT,
        "serializerFamily": DEFAULT_SERDE_FAMILY,
        "deserializerFamily": DEFAULT_SERDE_FAMILY,
        "schemaVersion": DEFAULT_SCHEMA_VERSION,
        "compatibilityMode": DEFAULT_COMPATIBILITY_MODE,
        "schemaVersioningPolicy": DEFAULT_SCHEMA_VERSIONING_POLICY,
        "registryCoordinates": DEFAULT_REGISTRY_COORDINATES,
    }


def _event_contract(
    *,
    schema_name: str,
    application_name: str,
    source_system: str,
    summary: str,
    payload_example: dict[str, Any] | None,
    match_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    header_contract = _header_contract()
    return {
        "schemaFormat": header_contract["schemaFormat"],
        "contentType": header_contract["contentType"],
        "serializerFamily": header_contract["serializerFamily"],
        "deserializerFamily": header_contract["deserializerFamily"],
        "schemaSubject": f"{application_name}.{schema_name}",
        "schemaVersion": header_contract["schemaVersion"],
        "schemaVersioningPolicy": header_contract["schemaVersioningPolicy"],
        "registryCoordinates": header_contract["registryCoordinates"],
        "compatibilityMode": header_contract["compatibilityMode"],
        "requiredHeaders": list(header_contract["requiredHeaders"]),
        "sourceSystem": source_system,
        "payloadExample": payload_example or {},
        "summary": summary,
        "matchStrategy": match_strategy or {"kind": "operation_invoked"},
    }


def _is_stripe_webhook_operation(
    path: str, tags: list[str], operation_id: str, summary: str
) -> bool:
    lowered = " ".join([path, operation_id, summary, *tags]).lower()
    return "stripe" in lowered and "webhook" in lowered


def _stripe_object_shape(stripe_type: str) -> dict[str, Any]:
    family = stripe_type.split(".", 1)[0]
    family_id = family.replace(".", "_")
    object_payload: dict[str, Any] = {
        "id": f"{family_id}_demo_123",
        "object": family.replace("_", "."),
        "amount": 4999,
        "currency": "usd",
        "status": stripe_type.rsplit(".", 1)[-1],
    }
    if family == "payment_intent":
        object_payload["customer"] = "cus_demo_123"
    if family == "charge":
        object_payload["payment_intent"] = "pi_demo_123"
    if family == "refund":
        object_payload["charge"] = "ch_demo_123"
    if family == "invoice":
        object_payload["subscription"] = "sub_demo_123"
    if family == "checkout":
        object_payload["payment_intent"] = "pi_demo_123"
    if family == "dispute":
        object_payload["charge"] = "ch_demo_123"
    return object_payload


def _stripe_payload_example(stripe_type: str) -> dict[str, Any]:
    return {
        "id": f"evt_{_safe_slug(stripe_type).replace('-', '_')}_demo_123",
        "type": stripe_type,
        "api_version": "2025-01-27.acacia",
        "created": 1767225600,
        "livemode": False,
        "data": {
            "object": _stripe_object_shape(stripe_type),
        },
    }


def _stripe_event_candidates(domain: str, source: str, application_name: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for stripe_type, event_name, topic_suffix in STRIPE_EVENT_CATALOG:
        schema_name = f"{event_name}Payload"
        candidates.append(
            {
                "canonicalEventName": event_name,
                "topicName": f"{domain}/{source}/{topic_suffix}/v1",
                "schemaName": schema_name,
                "applicationName": application_name,
                **_event_contract(
                    schema_name=schema_name,
                    application_name=application_name,
                    source_system="stripe",
                    summary=f"{event_name} emitted from Stripe webhook ingress.",
                    payload_example=_stripe_payload_example(stripe_type),
                    match_strategy={"kind": "stripe_event_type", "stripeType": stripe_type},
                ),
            }
        )
    return candidates


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
            is_stripe_webhook = _is_stripe_webhook_operation(path, tags, operation_id, summary)
            emits_event = _emit_business_event(method, tags, path)
            application_name = f"{service_name}-integration"

            event_candidates: list[dict[str, Any]] = []
            if is_stripe_webhook:
                stripe_enabled = True
                event_candidates = [
                    {**candidate, "operationId": operation_id, "emitsEvent": True}
                    for candidate in _stripe_event_candidates(
                        domain or "payments",
                        "stripe",
                        application_name,
                    )
                ]
                emits_event = True
            elif "stripe" in source:
                emits_event = False
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
                        **_event_contract(
                            schema_name=schema_name,
                            application_name=application_name,
                            source_system=source,
                            summary=f"{canonical_event_name} emitted from {operation_id}.",
                            payload_example=_example_from_schema(request_schema),
                        ),
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
                    "stripeWebhook": is_stripe_webhook,
                    "eventCandidates": event_candidates,
                }
            )
            if emits_event:
                payload = _example_from_schema(request_schema)
                if is_stripe_webhook and event_candidates:
                    payload = event_candidates[0].get("payloadExample") or payload
                test_fixtures.append(
                    {
                        "operationId": operation_id,
                        "label": f"{method.upper()} {path}",
                        "method": method.upper(),
                        "path": _fixture_path(path, parameters),
                        "payload": payload,
                    }
                )

    return {
        "title": title,
        "serviceName": service_name,
        "serviceVersion": service_version,
        "sourceMode": "openapi",
        "adapterType": "rest-ingress",
        "runtimeBlueprint": "rest_ingress",
        "servers": [server.get("url", "") for server in doc.get("servers", [])],
        "authSchemes": auth_schemes,
        "operations": operations,
        "topics": sorted(topics),
        "schemaNames": sorted(schema_names),
        "applicationNames": sorted(application_names or {f"{service_name}-integration"}),
        "stripeEnabled": stripe_enabled,
        "headerContract": _header_contract(),
        "compatibilityPolicy": DEFAULT_COMPATIBILITY_MODE,
        "testFixtures": test_fixtures,
    }
