"""Kafka/MQTT streaming source adapter.

Accepts a broker connection spec (JSON) and generates a streaming
source micro-integration that consumes from Kafka/MQTT topics and
publishes to Solace topics.
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


class KafkaSourceAdapter(SourceAdapter):
    source_type = "kafka"
    accepted_extensions = [".json"]
    accepted_content_types = ["application/json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("Kafka spec must be a JSON object")
        if "topics" not in doc and "brokers" not in doc:
            raise ValueError("Kafka spec must contain 'topics' or 'brokers' key")
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        topics = document.get("topics", [])
        service_name = _safe_slug(document.get("name", "kafka-source"))
        return SourceSummary(
            service_name=service_name,
            summary={
                "title": document.get("name", "Kafka Source"),
                "serviceName": service_name,
                "brokerType": "kafka",
                "topicCount": len(topics),
                "operationCount": len(topics),
            },
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        service_name = _safe_slug(document.get("name", "kafka-source"))
        application_name = f"{service_name}-integration"
        source_topics = document.get("topics", [])
        consumer_group = document.get("consumer_group", f"{service_name}-group")

        operations: list[dict[str, Any]] = []
        solace_topics: set[str] = set()
        schema_names: set[str] = set()

        for topic_spec in source_topics:
            topic_name = topic_spec if isinstance(topic_spec, str) else topic_spec.get("name", "")
            if not topic_name:
                continue
            entity_slug = _safe_slug(topic_name)
            entity_pascal = _pascal(entity_slug)
            op_id = f"consume{entity_pascal}"
            solace_topic = f"{service_name}/{entity_slug}/received/v1"
            event_name = f"{entity_pascal}Received"
            schema_name = f"{event_name}Payload"
            solace_topics.add(solace_topic)
            schema_names.add(schema_name)

            operations.append(
                {
                    "operationId": op_id,
                    "method": "SUBSCRIBE",
                    "path": topic_name,
                    "summary": f"Consume from Kafka topic {topic_name}",
                    "tags": [entity_slug],
                    "requestSchemaName": None,
                    "responseSchemaName": None,
                    "requestSchema": None,
                    "responseSchema": None,
                    "emitsEvent": True,
                    "eventCandidates": [
                        {
                            "operationId": op_id,
                            "canonicalEventName": event_name,
                            "topicName": solace_topic,
                            "schemaName": schema_name,
                            "applicationName": application_name,
                            "emitsEvent": True,
                        }
                    ],
                }
            )

        streaming_config = {
            "enabled": True,
            "idempotency_enabled": True,
            "dlq_enabled": True,
            "parking_lot_enabled": True,
            "retry_max_attempts": 5,
            "consumer_concurrency": document.get("concurrency", 1),
            "consumer_group": consumer_group,
            "partitioning_enabled": True,
            "partition_count": document.get("partition_count", 4),
            "schema_registry_enabled": document.get("schema_registry", False),
        }

        return SourceCanonicalResult(
            canonical_model={
                "title": document.get("name", "Kafka Source"),
                "serviceName": service_name,
                "serviceVersion": "1.0.0",
                "servers": document.get("brokers", []),
                "authSchemes": [],
                "operations": operations,
                "topics": sorted(solace_topics),
                "schemaNames": sorted(schema_names),
                "applicationNames": [application_name],
                "stripeEnabled": False,
                "testFixtures": [],
                "ingressType": "event_subscriber",
                "direction": "source",
                "streaming": streaming_config,
                "connectors": [
                    {
                        "id": "kafka-source",
                        "system_kind": "kafka",
                        "direction": "source",
                        "transport": "kafka",
                        "delivery_model": "stream",
                        "config": {
                            "brokers": document.get("brokers", []),
                            "topics": source_topics,
                            "consumer_group": consumer_group,
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
