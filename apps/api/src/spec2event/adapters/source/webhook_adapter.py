"""Generic webhook source adapter.

Accepts a webhook spec (JSON) describing incoming webhook endpoints
and generates a source MI that receives webhooks and publishes events
to Solace. Supports generic webhook signature verification.
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


class WebhookSourceAdapter(SourceAdapter):
    source_type = "webhook"
    accepted_extensions = [".json"]
    accepted_content_types = ["application/json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("Webhook spec must be a JSON object")
        if "endpoints" not in doc and "events" not in doc:
            raise ValueError(
                "Webhook spec must contain 'endpoints' or 'events' key"
            )
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        endpoints = document.get("endpoints", document.get("events", []))
        service_name = _safe_slug(document.get("name", "webhook-source"))
        return SourceSummary(
            service_name=service_name,
            summary={
                "title": document.get("name", "Webhook Source"),
                "serviceName": service_name,
                "endpointCount": len(endpoints),
                "operationCount": len(endpoints),
                "signatureVerification": document.get(
                    "signature_verification", False
                ),
            },
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        service_name = _safe_slug(document.get("name", "webhook-source"))
        application_name = f"{service_name}-integration"
        endpoints = document.get("endpoints", document.get("events", []))
        sig_verification = document.get("signature_verification", False)

        operations: list[dict[str, Any]] = []
        topics: set[str] = set()
        schema_names: set[str] = set()
        test_fixtures: list[dict[str, Any]] = []

        for endpoint in endpoints:
            if isinstance(endpoint, str):
                endpoint = {"name": endpoint, "path": f"/webhooks/{_safe_slug(endpoint)}"}
            name = endpoint.get("name", "webhook-event")
            path = endpoint.get("path", f"/webhooks/{_safe_slug(name)}")
            entity_slug = _safe_slug(name)
            entity_pascal = _pascal(entity_slug)
            op_id = f"receive{entity_pascal}"
            topic = f"{service_name}/{entity_slug}/received/v1"
            event_name = f"{entity_pascal}Received"
            schema_name = f"{event_name}Payload"
            topics.add(topic)
            schema_names.add(schema_name)

            operations.append(
                {
                    "operationId": op_id,
                    "method": "POST",
                    "path": path,
                    "summary": f"Receive {name} webhook",
                    "tags": [entity_slug],
                    "requestSchemaName": None,
                    "responseSchemaName": None,
                    "requestSchema": endpoint.get("schema"),
                    "responseSchema": None,
                    "emitsEvent": True,
                    "eventCandidates": [
                        {
                            "operationId": op_id,
                            "canonicalEventName": event_name,
                            "topicName": topic,
                            "schemaName": schema_name,
                            "applicationName": application_name,
                            "emitsEvent": True,
                        }
                    ],
                }
            )
            test_fixtures.append(
                {
                    "operationId": op_id,
                    "label": f"POST {path}",
                    "method": "POST",
                    "path": path,
                    "payload": endpoint.get("example_payload", {"event": name}),
                }
            )

        return SourceCanonicalResult(
            canonical_model={
                "title": document.get("name", "Webhook Source"),
                "serviceName": service_name,
                "serviceVersion": "1.0.0",
                "servers": [],
                "authSchemes": (
                    ["webhook_signature"] if sig_verification else []
                ),
                "operations": operations,
                "topics": sorted(topics),
                "schemaNames": sorted(schema_names),
                "applicationNames": [application_name],
                "stripeEnabled": False,
                "testFixtures": test_fixtures,
                "ingressType": "rest_controller",
                "direction": "source",
                "connectors": [
                    {
                        "id": "webhook-receiver",
                        "system_kind": "webhook",
                        "direction": "source",
                        "transport": "http",
                        "delivery_model": "push",
                        "config": {
                            "signature_verification": sig_verification,
                            "signature_header": document.get(
                                "signature_header", "X-Webhook-Signature"
                            ),
                        },
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
        )
