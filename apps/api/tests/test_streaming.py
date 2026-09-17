"""Tests for streaming-first hardening (Phase 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


def _streaming_canonical(streaming_config: dict | None = None) -> dict:
    """Canonical model with streaming enabled."""
    config = streaming_config or {
        "enabled": True,
        "idempotency_enabled": True,
        "dlq_enabled": True,
        "parking_lot_enabled": True,
        "retry_max_attempts": 3,
        "backoff_initial_ms": 1000,
        "backoff_max_ms": 30000,
        "backoff_multiplier": 2.0,
        "consumer_concurrency": 2,
        "partitioning_enabled": True,
        "partition_count": 4,
        "schema_registry_enabled": False,
    }
    return {
        "title": "Order Stream",
        "serviceName": "order-stream",
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "operations": [
            {
                "operationId": "orderEvent",
                "method": "POST",
                "path": "/orders",
                "summary": "Order events",
                "tags": [],
                "requestSchemaName": None,
                "responseSchemaName": None,
                "requestSchema": None,
                "responseSchema": None,
                "emitsEvent": True,
                "eventCandidates": [
                    {
                        "operationId": "orderEvent",
                        "canonicalEventName": "OrderCreated",
                        "topicName": "orders/created/v1",
                        "schemaName": "OrderCreatedPayload",
                        "applicationName": "order-stream-app",
                        "emitsEvent": True,
                    }
                ],
            }
        ],
        "topics": ["orders/created/v1"],
        "schemaNames": ["OrderCreatedPayload"],
        "applicationNames": ["order-stream-app"],
        "stripeEnabled": False,
        "testFixtures": [],
        "ingressType": "event_subscriber",
        "streaming": config,
    }


class TestStreamingGeneration:
    def test_streaming_generates_idempotency_service(self) -> None:
        ws = generator_service.generate("s-idem", _streaming_canonical(), {}, "")
        path = (
            ws / "src/main/java/com/spec2event/generated/service/IdempotencyService.java"
        )
        assert path.exists()
        content = path.read_text()
        assert "isDuplicate" in content
        assert "markProcessed" in content
        assert "evictExpired" in content

    def test_streaming_generates_dlq_service(self) -> None:
        ws = generator_service.generate("s-dlq", _streaming_canonical(), {}, "")
        path = (
            ws / "src/main/java/com/spec2event/generated/service/DeadLetterService.java"
        )
        assert path.exists()
        content = path.read_text()
        assert "routeFailedMessage" in content
        assert "parking-lot" in content
        assert "max-dlq-attempts" in content

    def test_streaming_generates_metrics_service(self) -> None:
        ws = generator_service.generate("s-metrics", _streaming_canonical(), {}, "")
        path = (
            ws
            / "src/main/java/com/spec2event/generated/service"
            / "StreamingMetricsService.java"
        )
        assert path.exists()
        content = path.read_text()
        assert "mi.messages.received" in content
        assert "mi.messages.processed" in content
        assert "mi.messages.failed" in content
        assert "mi.consumer.lag" in content

    def test_streaming_generates_config(self) -> None:
        ws = generator_service.generate("s-config", _streaming_canonical(), {}, "")
        path = ws / "config/application-streaming.yml"
        assert path.exists()
        content = path.read_text()
        assert "max-attempts: 3" in content
        assert "back-off-initial-interval: 1000" in content
        assert "partitioned: true" in content
        assert "partition-count: 4" in content
        assert "idempotency:" in content
        assert "parking-lot:" in content

    def test_streaming_with_schema_registry(self) -> None:
        config = {
            "enabled": True,
            "schema_registry_enabled": True,
        }
        ws = generator_service.generate("s-schema", _streaming_canonical(config), {}, "")
        content = (ws / "config/application-streaming.yml").read_text()
        assert "schema-registry-client" in content

    def test_streaming_disabled_skips_files(self) -> None:
        """When streaming.enabled is False, no streaming files are generated."""
        canonical = _streaming_canonical({"enabled": False})
        ws = generator_service.generate("s-disabled", canonical, {}, "")
        assert not (ws / "config/application-streaming.yml").exists()
        assert not (
            ws
            / "src/main/java/com/spec2event/generated/service/IdempotencyService.java"
        ).exists()

    def test_no_streaming_key_skips_files(self) -> None:
        """When no streaming config is present, no streaming files are generated."""
        canonical = _streaming_canonical()
        canonical.pop("streaming")
        ws = generator_service.generate("s-absent", canonical, {}, "")
        assert not (ws / "config/application-streaming.yml").exists()
