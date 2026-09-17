"""Declarative integration spec adapter.

Accepts a short JSON spec describing the desired integration
(input system, output system, transform, direction, delivery model)
and maps it directly onto the connector/workflow/transform contract.

This allows generating an MI from a concise declaration rather than
a full API spec or connection config.
"""

from __future__ import annotations

import json
from typing import Any

from spec2event.adapters.source.base import (
    SourceAdapter,
    SourceCanonicalResult,
    SourceParseResult,
    SourceSummary,
)
from spec2event.services.utils import pascal as _pascal
from spec2event.services.utils import safe_slug as _safe_slug


class IntegrationSpecAdapter(SourceAdapter):
    source_type = "integration_spec"
    accepted_extensions = [".json"]
    accepted_content_types = ["application/json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("Integration spec must be a JSON object")
        if "input_system" not in doc and "integration" not in doc:
            raise ValueError(
                "Integration spec must contain 'input_system' or 'integration' key"
            )
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        name = document.get("name", "custom-integration")
        service_name = _safe_slug(name)
        return SourceSummary(
            service_name=service_name,
            summary={
                "title": name,
                "serviceName": service_name,
                "inputSystem": document.get("input_system", "unknown"),
                "outputSystem": document.get("output_system", "solace"),
                "direction": document.get("direction", "source"),
                "transform": document.get("transform", "passthrough"),
            },
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        name = document.get("name", "custom-integration")
        service_name = _safe_slug(name)
        application_name = f"{service_name}-integration"
        direction = document.get("direction", "source")
        input_system = document.get("input_system", "rest")
        output_system = document.get("output_system", "solace")
        transform_engine = document.get("transform", "passthrough")
        delivery_model = document.get("delivery_model", "push")
        events = document.get("events", [])

        # Map input system to ingress type
        ingress_type_map = {
            "rest": "rest_controller",
            "webhook": "rest_controller",
            "http": "rest_controller",
            "database": "event_subscriber",
            "kafka": "event_subscriber",
            "mqtt": "event_subscriber",
            "amqp": "event_subscriber",
            "file": "polling_consumer",
            "sftp": "polling_consumer",
            "s3": "polling_consumer",
        }
        ingress_type = ingress_type_map.get(input_system, "rest_controller")

        # Build operations from events or generate defaults
        operations: list[dict[str, Any]] = []
        topics: set[str] = set()
        schema_names: set[str] = set()

        if not events:
            events = [{"name": f"{name}-event"}]

        for event_spec in events:
            event_name_raw = (
                event_spec if isinstance(event_spec, str)
                else event_spec.get("name", "event")
            )
            event_slug = _safe_slug(event_name_raw)
            event_pascal = _pascal(event_slug)
            op_id = f"process{event_pascal}"
            topic = f"{service_name}/{event_slug}/v1"
            schema_name = f"{event_pascal}Payload"
            topics.add(topic)
            schema_names.add(schema_name)

            operations.append({
                "operationId": op_id,
                "method": "EVENT",
                "path": f"/{event_slug}",
                "summary": f"Process {event_name_raw}",
                "tags": [event_slug],
                "requestSchemaName": None,
                "responseSchemaName": None,
                "requestSchema": None,
                "responseSchema": None,
                "emitsEvent": True,
                "eventCandidates": [{
                    "operationId": op_id,
                    "canonicalEventName": event_pascal,
                    "topicName": topic,
                    "schemaName": schema_name,
                    "applicationName": application_name,
                    "emitsEvent": True,
                }],
            })

        # Determine target pattern for target/bidi direction
        target_pattern = ""
        if direction in ("target", "bidirectional"):
            target_pattern_map = {
                "rest": "rest_sink",
                "webhook": "rest_sink",
                "http": "rest_sink",
                "database": "generic_target",
                "kafka": "generic_target",
            }
            target_pattern = target_pattern_map.get(
                output_system, "generic_target"
            )

        # Streaming config for streaming sources
        streaming_config: dict[str, Any] = {}
        if delivery_model == "stream" or input_system in (
            "kafka", "mqtt", "database"
        ):
            streaming_config = {
                "enabled": True,
                "idempotency_enabled": True,
                "dlq_enabled": True,
                "parking_lot_enabled": True,
            }

        canonical: dict[str, Any] = {
            "title": name,
            "serviceName": service_name,
            "serviceVersion": "1.0.0",
            "servers": [],
            "authSchemes": [],
            "operations": operations,
            "topics": sorted(topics),
            "schemaNames": sorted(schema_names),
            "applicationNames": [application_name],
            "stripeEnabled": False,
            "testFixtures": [],
            "ingressType": ingress_type,
            "direction": direction,
            "connectors": [
                {
                    "id": f"{input_system}-connector",
                    "system_kind": input_system,
                    "direction": "source",
                    "transport": input_system,
                    "delivery_model": delivery_model,
                },
                {
                    "id": "solace",
                    "system_kind": "solace",
                    "direction": "target",
                    "transport": "solace",
                    "delivery_model": "push",
                },
            ],
        }

        if target_pattern:
            canonical["targetPattern"] = target_pattern

        if transform_engine != "passthrough":
            canonical["transformEngine"] = transform_engine
            canonical["transformSpec"] = document.get("transform_config", {"config": {}})

        if streaming_config:
            canonical["streaming"] = streaming_config

        return SourceCanonicalResult(canonical_model=canonical)
