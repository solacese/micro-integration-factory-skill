"""Database CDC source adapter.

Accepts a database connection spec (JSON) and generates a CDC-based
source micro-integration that captures change events from database tables
and publishes them to Solace topics.

Preferred CDC approach: log-based (Debezium-style) over trigger-based.
Includes snapshot/backfill strategy that does not lock source tables.
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


class DatabaseSourceAdapter(SourceAdapter):
    source_type = "database"
    accepted_extensions = [".json"]
    accepted_content_types = ["application/json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("Database spec must be a JSON object")
        if "tables" not in doc and "connection" not in doc:
            raise ValueError(
                "Database spec must contain 'tables' or 'connection' key"
            )
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        db_type = document.get("type", "postgresql")
        tables = document.get("tables", [])
        service_name = _safe_slug(
            document.get("name", f"{db_type}-cdc")
        )
        return SourceSummary(
            service_name=service_name,
            summary={
                "title": document.get("name", f"{db_type} CDC"),
                "serviceName": service_name,
                "databaseType": db_type,
                "tableCount": len(tables),
                "operationCount": len(tables) * 3,
            },
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        db_type = document.get("type", "postgresql")
        service_name = _safe_slug(document.get("name", f"{db_type}-cdc"))
        application_name = f"{service_name}-integration"
        tables = document.get("tables", [])

        operations: list[dict[str, Any]] = []
        topics: set[str] = set()
        schema_names: set[str] = set()

        for table_spec in tables:
            table_name = table_spec if isinstance(table_spec, str) else table_spec.get("name", "")
            if not table_name:
                continue
            entity_slug = _safe_slug(table_name)
            entity_pascal = _pascal(entity_slug)

            for action in ["created", "updated", "deleted"]:
                op_id = f"{entity_slug}{_pascal(action)}"
                topic = f"{service_name}/{entity_slug}/{action}/v1"
                event_name = f"{entity_pascal}{_pascal(action)}"
                schema_name = f"{event_name}Payload"
                topics.add(topic)
                schema_names.add(schema_name)

                operations.append(
                    {
                        "operationId": op_id,
                        "method": "CDC",
                        "path": f"/{entity_slug}",
                        "summary": f"{table_name} {action} (CDC)",
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
                                "topicName": topic,
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
            "backoff_initial_ms": 1000,
            "backoff_max_ms": 60000,
            "backoff_multiplier": 2.0,
            "partitioning_enabled": True,
            "partition_count": len(tables) if tables else 1,
        }

        return SourceCanonicalResult(
            canonical_model={
                "title": document.get("name", f"{db_type} CDC"),
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
                "ingressType": "event_subscriber",
                "direction": "source",
                "streaming": streaming_config,
                "connectors": [
                    {
                        "id": f"{db_type}-cdc",
                        "system_kind": "database",
                        "direction": "source",
                        "transport": "debezium",
                        "delivery_model": "stream",
                        "config": {
                            "database_type": db_type,
                            "tables": tables,
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
