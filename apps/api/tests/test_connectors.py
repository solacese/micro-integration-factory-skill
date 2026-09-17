"""Tests for new source adapters (database, kafka, webhook)."""

from __future__ import annotations

from pathlib import Path

import pytest

import spec2event.adapters.source  # noqa: F401 (triggers registration)
from spec2event.adapters.source.registry import available_source_types, get_source_adapter
from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


class TestSourceRegistry:
    def test_all_adapters_registered(self) -> None:
        types = available_source_types()
        assert "openapi" in types
        assert "json_schema" in types
        assert "database" in types
        assert "kafka" in types
        assert "webhook" in types


class TestDatabaseAdapter:
    SAMPLE = API_ROOT / "resources" / "samples" / "database" / "orders-cdc.json"

    def test_parse(self) -> None:
        adapter = get_source_adapter("database")
        result = adapter.parse(self.SAMPLE.read_text())
        assert "tables" in result.document
        assert len(result.document["tables"]) == 3

    def test_summarize(self) -> None:
        adapter = get_source_adapter("database")
        parsed = adapter.parse(self.SAMPLE.read_text())
        summary = adapter.summarize(parsed.document)
        assert summary.service_name == "orders-cdc"
        assert summary.summary["tableCount"] == 3

    def test_canonicalize(self) -> None:
        adapter = get_source_adapter("database")
        parsed = adapter.parse(self.SAMPLE.read_text())
        result = adapter.canonicalize(parsed.document)
        cm = result.canonical_model
        assert cm["ingressType"] == "event_subscriber"
        assert cm["direction"] == "source"
        assert len(cm["operations"]) == 9  # 3 tables * 3 actions
        assert cm["streaming"]["enabled"] is True

    def test_generates_workspace(self) -> None:
        adapter = get_source_adapter("database")
        spec = self.SAMPLE.read_text()
        parsed = adapter.parse(spec)
        summary = adapter.summarize(parsed.document)
        cm = adapter.canonicalize(parsed.document).canonical_model
        ws = generator_service.generate("db-test", cm, summary.summary, spec)
        assert (ws / "pom.xml").exists()
        assert (ws / "config/application-streaming.yml").exists()


class TestKafkaAdapter:
    SAMPLE = API_ROOT / "resources" / "samples" / "kafka" / "order-events.json"

    def test_parse(self) -> None:
        adapter = get_source_adapter("kafka")
        result = adapter.parse(self.SAMPLE.read_text())
        assert "topics" in result.document
        assert len(result.document["topics"]) == 3

    def test_summarize(self) -> None:
        adapter = get_source_adapter("kafka")
        parsed = adapter.parse(self.SAMPLE.read_text())
        summary = adapter.summarize(parsed.document)
        assert summary.service_name == "order-events-kafka"

    def test_canonicalize(self) -> None:
        adapter = get_source_adapter("kafka")
        parsed = adapter.parse(self.SAMPLE.read_text())
        result = adapter.canonicalize(parsed.document)
        cm = result.canonical_model
        assert cm["ingressType"] == "event_subscriber"
        assert cm["streaming"]["enabled"] is True
        assert cm["streaming"]["schema_registry_enabled"] is True
        assert len(cm["operations"]) == 3

    def test_generates_workspace(self) -> None:
        adapter = get_source_adapter("kafka")
        spec = self.SAMPLE.read_text()
        parsed = adapter.parse(spec)
        summary = adapter.summarize(parsed.document)
        cm = adapter.canonicalize(parsed.document).canonical_model
        ws = generator_service.generate("kafka-test", cm, summary.summary, spec)
        assert (ws / "pom.xml").exists()
        assert (ws / "config/application-streaming.yml").exists()


class TestWebhookAdapter:
    SAMPLE = API_ROOT / "resources" / "samples" / "webhook" / "payment-webhooks.json"

    def test_parse(self) -> None:
        adapter = get_source_adapter("webhook")
        result = adapter.parse(self.SAMPLE.read_text())
        assert "endpoints" in result.document
        assert len(result.document["endpoints"]) == 3

    def test_summarize(self) -> None:
        adapter = get_source_adapter("webhook")
        parsed = adapter.parse(self.SAMPLE.read_text())
        summary = adapter.summarize(parsed.document)
        assert summary.service_name == "payment-webhooks"
        assert summary.summary["signatureVerification"] is True

    def test_canonicalize(self) -> None:
        adapter = get_source_adapter("webhook")
        parsed = adapter.parse(self.SAMPLE.read_text())
        result = adapter.canonicalize(parsed.document)
        cm = result.canonical_model
        assert cm["ingressType"] == "rest_controller"
        assert len(cm["operations"]) == 3
        assert len(cm["testFixtures"]) == 3

    def test_generates_workspace(self) -> None:
        adapter = get_source_adapter("webhook")
        spec = self.SAMPLE.read_text()
        parsed = adapter.parse(spec)
        summary = adapter.summarize(parsed.document)
        cm = adapter.canonicalize(parsed.document).canonical_model
        ws = generator_service.generate("webhook-test", cm, summary.summary, spec)
        assert (ws / "pom.xml").exists()
        assert (
            ws / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java"
        ).exists()
