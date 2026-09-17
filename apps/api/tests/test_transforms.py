"""Tests for the transform engine registry and generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service
from spec2event.transforms import (
    available_transform_engines,
    get_transform_engine,
)


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


def _minimal_canonical(engine_id: str, config: dict | None = None) -> dict:
    """Create a minimal canonical model with a specific transform engine."""
    return {
        "title": f"Test {engine_id}",
        "serviceName": f"test-{engine_id}",
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "operations": [
            {
                "operationId": "testOp",
                "method": "POST",
                "path": "/test",
                "summary": "Test operation",
                "tags": [],
                "requestSchemaName": None,
                "responseSchemaName": None,
                "requestSchema": None,
                "responseSchema": None,
                "emitsEvent": True,
                "eventCandidates": [
                    {
                        "operationId": "testOp",
                        "canonicalEventName": "TestEvent",
                        "topicName": "test/event/v1",
                        "schemaName": "TestPayload",
                        "applicationName": "test-app",
                        "emitsEvent": True,
                    }
                ],
            }
        ],
        "topics": ["test/event/v1"],
        "schemaNames": ["TestPayload"],
        "applicationNames": ["test-app"],
        "stripeEnabled": False,
        "testFixtures": [],
        "ingressType": "rest_controller",
        "transformEngine": engine_id,
        "transformSpec": {"config": config or {}},
    }


class TestTransformRegistry:
    def test_all_engines_registered(self) -> None:
        engines = available_transform_engines()
        assert "passthrough" in engines
        assert "field_mapping" in engines
        assert "jolt" in engines
        assert "dataweave" in engines
        assert "scripting" in engines
        assert "custom_java" in engines

    def test_get_unknown_engine(self) -> None:
        assert get_transform_engine("nonexistent") is None

    def test_each_engine_has_fixtures(self) -> None:
        for engine_id in available_transform_engines():
            engine = get_transform_engine(engine_id)
            assert engine is not None
            assert len(engine.fixtures) >= 1, f"{engine_id} has no fixtures"


class TestTransformGeneration:
    def test_passthrough_generates_java(self) -> None:
        ws = generator_service.generate("t-pass", _minimal_canonical("passthrough"), {}, "")
        path = ws / "src/main/java/com/spec2event/generated/transform/PassthroughTransform.java"
        assert path.exists()
        content = path.read_text()
        assert "class PassthroughTransform" in content
        assert "Function<JsonNode, JsonNode>" in content

    def test_field_mapping_generates_java(self) -> None:
        config = {"mappings": [{"source": "order_id", "target": "orderId"}]}
        canonical = _minimal_canonical("field_mapping", config)
        ws = generator_service.generate("t-map", canonical, {}, "")
        path = ws / "src/main/java/com/spec2event/generated/transform/FieldMappingTransform.java"
        assert path.exists()
        content = path.read_text()
        assert "order_id" in content
        assert "orderId" in content

    def test_jolt_generates_java_and_spec(self) -> None:
        ws = generator_service.generate("t-jolt", _minimal_canonical("jolt"), {}, "")
        java_path = ws / "src/main/java/com/spec2event/generated/transform/JoltTransform.java"
        spec_path = ws / "src/main/resources/transforms/jolt-spec.json"
        assert java_path.exists()
        assert spec_path.exists()
        assert "Chainr" in java_path.read_text()

    def test_dataweave_generates_java_and_dwl(self) -> None:
        ws = generator_service.generate("t-dw", _minimal_canonical("dataweave"), {}, "")
        java_path = ws / "src/main/java/com/spec2event/generated/transform/DataWeaveTransform.java"
        dwl_path = ws / "src/main/resources/transforms/transform.dwl"
        assert java_path.exists()
        assert dwl_path.exists()
        assert "%dw 2.0" in dwl_path.read_text()

    def test_scripting_generates_java_and_script(self) -> None:
        ws = generator_service.generate("t-script", _minimal_canonical("scripting"), {}, "")
        java_path = ws / "src/main/java/com/spec2event/generated/transform/ScriptTransform.java"
        script_path = ws / "src/main/resources/transforms/transform-script.js"
        assert java_path.exists()
        assert script_path.exists()

    def test_custom_java_generates_stub(self) -> None:
        ws = generator_service.generate("t-custom", _minimal_canonical("custom_java"), {}, "")
        path = ws / "src/main/java/com/spec2event/generated/transform/CustomTransform.java"
        assert path.exists()
        assert "TODO" in path.read_text()

    def test_no_transform_engine_skips_transform_files(self) -> None:
        """When no transformEngine is specified, no transform files are generated."""
        canonical = _minimal_canonical("passthrough")
        canonical.pop("transformEngine")
        ws = generator_service.generate("t-none", canonical, {}, "")
        transform_dir = ws / "src/main/java/com/spec2event/generated/transform"
        assert not transform_dir.exists()
