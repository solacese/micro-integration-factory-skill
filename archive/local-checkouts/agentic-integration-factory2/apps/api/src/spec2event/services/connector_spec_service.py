from __future__ import annotations

import json
import re
from typing import Any

FILE_LIKE_SOURCE_MODES = {"file", "sftp", "ftp", "object_storage"}
BRIDGE_SOURCE_MODES = {"mqtt", "kafka", "queue", "amqp", "jms"}
ADAPTER_TYPE_BY_SOURCE_MODE = {
    "webhook": "webhook-ingress",
    "file": "file-polling",
    "sftp": "sftp-file-polling",
    "ftp": "ftp-file-polling",
    "object_storage": "object-storage-listener",
    "mqtt": "mqtt-subscriber-bridge",
    "kafka": "kafka-consumer-bridge",
    "queue": "queue-bridge",
    "amqp": "amqp-consumer-bridge",
    "jms": "jms-consumer-bridge",
}
RUNTIME_BLUEPRINT_BY_SOURCE_MODE = {
    "webhook": "webhook_ingress",
    "file": "file_poller",
    "sftp": "file_poller",
    "ftp": "file_poller",
    "object_storage": "file_poller",
    "mqtt": "bridge_starter",
    "kafka": "bridge_starter",
    "queue": "bridge_starter",
    "amqp": "bridge_starter",
    "jms": "bridge_starter",
}


def load_connector_spec(raw_content: str) -> dict[str, Any]:
    payload = json.loads(raw_content)
    if not isinstance(payload, dict):
        raise ValueError("Connector spec must be a JSON object")
    return payload


def summarize_connector_spec(spec: dict[str, Any]) -> dict[str, Any]:
    canonical_model = canonicalize_connector_spec(spec)
    return {
        "title": canonical_model["title"],
        "serviceName": canonical_model["serviceName"],
        "version": canonical_model["serviceVersion"],
        "sourceMode": canonical_model["sourceMode"],
        "adapterType": canonical_model["adapterType"],
        "runtimeBlueprint": canonical_model["runtimeBlueprint"],
        "operationCount": len(canonical_model["operations"]),
        "eventCount": sum(
            len(operation.get("eventCandidates", [])) for operation in canonical_model["operations"]
        ),
        "topics": canonical_model["topics"],
        "applicationDomainName": canonical_model.get("applicationDomainName"),
        "sourceDetails": canonical_model["sourceDetails"],
    }


def canonicalize_connector_spec(spec: dict[str, Any]) -> dict[str, Any]:
    source_mode = str(spec.get("sourceMode") or "").strip()
    if source_mode not in ADAPTER_TYPE_BY_SOURCE_MODE:
        supported = ", ".join(sorted(ADAPTER_TYPE_BY_SOURCE_MODE))
        raise ValueError(f"Unsupported source mode {source_mode!r}. Supported: {supported}")

    name = str(spec.get("name") or "").strip()
    if not name:
        raise ValueError("Connector spec name is required")

    service_name = _safe_slug(name)
    title = name
    service_version = str(spec.get("version") or "1.0.0")
    raw_source_details = spec.get("sourceDetails")
    source_details = raw_source_details if isinstance(raw_source_details, dict) else {}
    application_domain_name = spec.get("applicationDomainName")
    adapter_type = str(spec.get("connectorPattern") or ADAPTER_TYPE_BY_SOURCE_MODE[source_mode])
    runtime_blueprint = RUNTIME_BLUEPRINT_BY_SOURCE_MODE[source_mode]
    topic_root = _safe_slug(str(spec.get("topicRoot") or "integration"))
    application_name = f"{service_name}-integration"

    public_ingress_path = _public_ingress_path(source_mode, service_name, source_details)
    internal_emit_path = str(source_details.get("internalEmitPath") or "/internal/source/emit")
    internal_poll_path = str(source_details.get("internalPollPath") or "/internal/source/poll-now")

    events = spec.get("events") if isinstance(spec.get("events"), list) else []
    event_candidates = _event_candidates(
        source_mode=source_mode,
        service_name=service_name,
        application_name=application_name,
        topic_root=topic_root,
        raw_events=events,
    )
    schema_names = sorted(
        {
            candidate["schemaName"]
            for candidate in event_candidates
        }
    )

    request_schema = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "payload": {"type": "object", "additionalProperties": True},
            "metadata": {"type": "object", "additionalProperties": True},
        },
    }

    operation = {
        "operationId": _operation_id_for_source_mode(source_mode, service_name),
        "method": "POST",
        "path": public_ingress_path
        if source_mode == "webhook"
        else internal_poll_path
        if source_mode in FILE_LIKE_SOURCE_MODES
        else internal_emit_path,
        "summary": _operation_summary(source_mode, title, adapter_type),
        "tags": [source_mode, adapter_type],
        "requestSchemaName": f"{_pascal(service_name)}IngressPayload",
        "responseSchemaName": None,
        "requestSchema": request_schema,
        "responseSchema": None,
        "emitsEvent": True,
        "eventCandidates": event_candidates,
    }

    test_fixtures = _test_fixtures(
        source_mode=source_mode,
        operation_id=operation["operationId"],
        public_ingress_path=public_ingress_path,
        internal_emit_path=internal_emit_path,
        internal_poll_path=internal_poll_path,
        event_candidates=event_candidates,
        source_details=source_details,
    )

    return {
        "title": title,
        "serviceName": service_name,
        "serviceVersion": service_version,
        "sourceMode": source_mode,
        "adapterType": adapter_type,
        "runtimeBlueprint": runtime_blueprint,
        "applicationDomainName": application_domain_name,
        "description": spec.get("description"),
        "servers": [],
        "authSchemes": [],
        "operations": [operation],
        "topics": sorted(candidate["topicName"] for candidate in event_candidates),
        "schemaNames": sorted(
            {operation["requestSchemaName"], *schema_names}
        ),
        "applicationNames": [application_name],
        "stripeEnabled": False,
        "testFixtures": test_fixtures,
        "sourceDetails": source_details,
        "connectorSpec": spec,
        "publicIngressPath": public_ingress_path if source_mode == "webhook" else None,
        "internalEmitPath": internal_emit_path,
        "internalPollPath": internal_poll_path if source_mode in FILE_LIKE_SOURCE_MODES else None,
    }


def _event_candidates(
    *,
    source_mode: str,
    service_name: str,
    application_name: str,
    topic_root: str,
    raw_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not raw_events:
        raw_events = [
            {
                "name": f"{_pascal(service_name)}Observed",
                "entity": service_name,
                "action": "observed",
                "summary": f"Observed payload from the {source_mode} source",
            }
        ]

    candidates = []
    for index, raw_event in enumerate(raw_events, start=1):
        event_name = _pascal(str(raw_event.get("name") or f"{service_name}Event{index}"))
        entity = _safe_slug(str(raw_event.get("entity") or service_name))
        action = _safe_slug(str(raw_event.get("action") or "observed"))
        topic_name = str(
            raw_event.get("topicName")
            or f"{topic_root}/{service_name}/{entity}/{action}/v1"
        )
        schema_name = str(raw_event.get("schemaName") or f"{event_name}Payload")
        candidates.append(
            {
                "operationId": _operation_id_for_source_mode(source_mode, service_name),
                "canonicalEventName": event_name,
                "topicName": topic_name,
                "schemaName": schema_name,
                "applicationName": application_name,
                "emitsEvent": True,
                "payloadExample": raw_event.get("payloadExample") or {
                    "sourceMode": source_mode,
                    "serviceName": service_name,
                    "entity": entity,
                    "action": action,
                },
                "summary": raw_event.get("summary")
                or f"{event_name} emitted from the {source_mode} connector starter",
            }
        )
    return candidates


def _test_fixtures(
    *,
    source_mode: str,
    operation_id: str,
    public_ingress_path: str,
    internal_emit_path: str,
    internal_poll_path: str,
    event_candidates: list[dict[str, Any]],
    source_details: dict[str, Any],
) -> list[dict[str, Any]]:
    primary_payload = (
        event_candidates[0].get("payloadExample")
        if event_candidates
        else {"sourceMode": source_mode}
    )
    if source_mode == "webhook":
        return [
            {
                "operationId": operation_id,
                "label": f"POST {public_ingress_path}",
                "method": "POST",
                "path": public_ingress_path,
                "payload": primary_payload,
            }
        ]
    if source_mode in FILE_LIKE_SOURCE_MODES:
        return [
            {
                "operationId": operation_id,
                "label": f"POST {internal_poll_path}",
                "method": "POST",
                "path": internal_poll_path,
                "payload": {
                    "limit": 5,
                    "inputDirectory": source_details.get("inputDirectory")
                    or source_details.get("bucketPrefix")
                    or "./demo/inbox",
                },
            }
        ]
    return [
        {
            "operationId": operation_id,
            "label": f"POST {internal_emit_path}",
            "method": "POST",
            "path": internal_emit_path,
            "payload": {
                "payload": primary_payload,
                "metadata": {
                    "sourceMode": source_mode,
                    "sourceAddress": source_details.get("topic")
                    or source_details.get("queueName")
                    or source_details.get("stream")
                    or "demo-source",
                },
            },
        }
    ]


def _operation_summary(source_mode: str, title: str, adapter_type: str) -> str:
    if source_mode == "webhook":
        return f"Accept webhook payloads for {title} and publish canonical Solace events"
    if source_mode in FILE_LIKE_SOURCE_MODES:
        return f"Poll {source_mode} input for {title} and publish canonical Solace events"
    return f"Bridge {source_mode} messages for {title} into Solace via {adapter_type}"


def _operation_id_for_source_mode(source_mode: str, service_name: str) -> str:
    if source_mode == "webhook":
        return f"accept{_pascal(service_name)}Webhook"
    if source_mode in FILE_LIKE_SOURCE_MODES:
        return f"poll{_pascal(service_name)}Source"
    return f"bridge{_pascal(service_name)}Source"


def _public_ingress_path(
    source_mode: str,
    service_name: str,
    source_details: dict[str, Any],
) -> str:
    if source_mode != "webhook":
        return ""
    return str(source_details.get("publicPath") or f"/webhooks/{service_name}")


def _safe_slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "generated-service"


def _pascal(text: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)
