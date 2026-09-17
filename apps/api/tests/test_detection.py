"""Tests for source type auto-detection and declarative integration spec."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import spec2event.adapters.source  # noqa: F401
from spec2event.adapters.source.registry import get_source_adapter
from spec2event.config import get_settings
from spec2event.services.detection_service import detect_source_type
from spec2event.services.generator_service import generator_service

API_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


class TestDetection:
    def test_detect_openapi_by_extension(self) -> None:
        assert detect_source_type("", filename="petstore.yaml") == "openapi"
        assert detect_source_type("", filename="api.yml") == "openapi"

    def test_detect_openapi_by_content(self) -> None:
        content = "openapi: 3.0.0\ninfo:\n  title: Test"
        assert detect_source_type(content) == "openapi"

    def test_detect_json_schema_by_content(self) -> None:
        content = json.dumps({"$schema": "...", "type": "object", "properties": {}})
        assert detect_source_type(content) == "json_schema"

    def test_detect_database_by_content(self) -> None:
        content = json.dumps({"tables": ["orders"], "type": "postgresql"})
        assert detect_source_type(content) == "database"

    def test_detect_kafka_by_content(self) -> None:
        content = json.dumps({"topics": ["orders"], "brokers": ["localhost:9092"]})
        assert detect_source_type(content) == "kafka"

    def test_detect_webhook_by_content(self) -> None:
        content = json.dumps({"endpoints": [{"name": "test"}]})
        assert detect_source_type(content) == "webhook"

    def test_detect_integration_spec_by_content(self) -> None:
        content = json.dumps({"input_system": "kafka", "output_system": "rest"})
        assert detect_source_type(content) == "integration_spec"

    def test_explicit_override_wins(self) -> None:
        content = json.dumps({"tables": ["orders"]})
        assert detect_source_type(content, explicit_type="kafka") == "kafka"

    def test_explicit_override_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown source type"):
            detect_source_type("", explicit_type="nonexistent")

    def test_undetectable_raises(self) -> None:
        with pytest.raises(ValueError, match="Could not auto-detect"):
            detect_source_type("random unstructured text")

    def test_detect_openapi_json_format(self) -> None:
        content = json.dumps({"openapi": "3.0.0", "info": {"title": "Test"}})
        assert detect_source_type(content) == "openapi"

    def test_detect_by_content_type(self) -> None:
        assert detect_source_type(
            "", content_type="application/yaml"
        ) == "openapi"
        assert detect_source_type(
            "", content_type="application/schema+json"
        ) == "json_schema"


class TestIntegrationSpecAdapter:
    SAMPLE = API_ROOT / "resources" / "samples" / "integration_spec" / "kafka-to-rest.json"

    def test_parse(self) -> None:
        adapter = get_source_adapter("integration_spec")
        result = adapter.parse(self.SAMPLE.read_text())
        assert result.document["input_system"] == "kafka"
        assert result.document["output_system"] == "rest"

    def test_canonicalize_bidirectional(self) -> None:
        adapter = get_source_adapter("integration_spec")
        parsed = adapter.parse(self.SAMPLE.read_text())
        result = adapter.canonicalize(parsed.document)
        cm = result.canonical_model
        assert cm["direction"] == "bidirectional"
        assert cm["targetPattern"] == "rest_sink"
        assert cm["transformEngine"] == "field_mapping"
        assert cm["ingressType"] == "event_subscriber"
        assert len(cm["operations"]) == 3

    def test_generates_bidirectional_workspace(self) -> None:
        adapter = get_source_adapter("integration_spec")
        spec = self.SAMPLE.read_text()
        parsed = adapter.parse(spec)
        summary = adapter.summarize(parsed.document)
        cm = adapter.canonicalize(parsed.document).canonical_model
        ws = generator_service.generate("integ-test", cm, summary.summary, spec)
        assert (ws / "pom.xml").exists()
        # Source side (event subscriber)
        svc = ws / "src/main/java/com/spec2event/generated/service"
        assert (svc / "EventSubscriberService.java").exists()
        # Target side (REST sink)
        assert (svc / "SolaceConsumerService.java").exists()
        assert (svc / "RestTargetSinkService.java").exists()
        # Transform
        transform = ws / "src/main/java/com/spec2event/generated/transform"
        assert (transform / "FieldMappingTransform.java").exists()
        # Streaming
        assert (ws / "config/application-streaming.yml").exists()
