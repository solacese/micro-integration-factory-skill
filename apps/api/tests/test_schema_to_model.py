"""Tests for schema-to-typed-model generation (Phase 9)."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)
from spec2event.services.schema_to_model_service import extract_models_from_canonical

API_ROOT = Path(__file__).resolve().parents[1]
PETSTORE = API_ROOT / "resources" / "samples" / "openapi" / "petstore.yaml"


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


class TestSchemaToModel:
    def test_extract_models_from_petstore(self) -> None:
        spec = PETSTORE.read_text()
        doc = load_openapi_document(spec)
        canonical = canonicalize_openapi(doc)
        models = extract_models_from_canonical(canonical)
        assert len(models) > 0
        names = [m["model_name"] for m in models]
        # Petstore has Pet, Order, User schemas
        assert any("Pet" in n for n in names)

    def test_model_fields_have_java_types(self) -> None:
        spec = PETSTORE.read_text()
        doc = load_openapi_document(spec)
        canonical = canonicalize_openapi(doc)
        models = extract_models_from_canonical(canonical)
        for model in models:
            for field in model["model_fields"]:
                assert "java_type" in field
                assert "java_name" in field
                assert "json_name" in field
                assert field["java_type"]  # not empty

    def test_generate_typed_models_opt_in(self) -> None:
        """Typed models are only generated when generateTypedModels is True."""
        spec = PETSTORE.read_text()
        doc = load_openapi_document(spec)
        canonical = canonicalize_openapi(doc)
        summary = summarize_openapi(doc)

        # Without opt-in
        canonical["generateTypedModels"] = False
        ws = generator_service.generate("no-models", canonical, summary, spec)
        model_dir = ws / "src/main/java/com/spec2event/generated/model"
        assert not model_dir.exists()

    def test_generate_typed_models_produces_java(self) -> None:
        """With opt-in, typed models are generated as Java files."""
        spec = PETSTORE.read_text()
        doc = load_openapi_document(spec)
        canonical = canonicalize_openapi(doc)
        canonical["generateTypedModels"] = True
        summary = summarize_openapi(doc)

        ws = generator_service.generate("with-models", canonical, summary, spec)
        model_dir = ws / "src/main/java/com/spec2event/generated/model"
        assert model_dir.exists()
        java_files = list(model_dir.glob("*.java"))
        assert len(java_files) > 0

        # Verify content of one model
        for f in java_files:
            content = f.read_text()
            assert "package com.spec2event.generated.model;" in content
            assert "@JsonProperty" in content
            assert "public class" in content

    def test_type_mapping_string(self) -> None:
        from spec2event.services.schema_to_model_service import _json_type_to_java

        assert _json_type_to_java({"type": "string"}) == "String"
        assert _json_type_to_java({"type": "string", "format": "date-time"}) == "java.time.Instant"
        assert _json_type_to_java({"type": "string", "format": "uuid"}) == "java.util.UUID"

    def test_type_mapping_numeric(self) -> None:
        from spec2event.services.schema_to_model_service import _json_type_to_java

        assert _json_type_to_java({"type": "integer"}) == "Integer"
        assert _json_type_to_java({"type": "integer", "format": "int64"}) == "Long"
        assert _json_type_to_java({"type": "number"}) == "Double"

    def test_type_mapping_array(self) -> None:
        from spec2event.services.schema_to_model_service import _json_type_to_java

        result = _json_type_to_java({"type": "array", "items": {"type": "string"}})
        assert result == "java.util.List<String>"
