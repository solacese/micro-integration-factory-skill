"""Built-in transformation engines.

Each engine renders a Java class (or config file) that performs the
message transformation between source and target binders.
"""

from __future__ import annotations

from typing import Any

from spec2event.transforms.base import (
    TransformEngine,
    TransformFixture,
    TransformOutput,
    register_transform,
)

_BASE = "src/main/java/com/spec2event/generated/transform"


# ---------------------------------------------------------------------------
# Passthrough (no-op, default)
# ---------------------------------------------------------------------------


class PassthroughTransformEngine(TransformEngine):
    """Passes messages through without modification (default)."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="passthrough",
            display_name="Passthrough",
            description="No transformation; messages pass through unchanged.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/PassthroughTransform.java",
                    template_name="integration-java-mdk/transforms/PassthroughTransform.java.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="identity",
                    input_payload={"orderId": "123", "amount": 99.99},
                    expected_output={"orderId": "123", "amount": 99.99},
                    description="Input passes through unchanged",
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Field Mapping (declarative)
# ---------------------------------------------------------------------------


class FieldMappingTransformEngine(TransformEngine):
    """Declarative field mapping (rename, select, flatten)."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="field_mapping",
            display_name="Field Mapping",
            description="Declarative field renaming, selection, and flattening.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/FieldMappingTransform.java",
                    template_name="integration-java-mdk/transforms/FieldMappingTransform.java.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="rename_fields",
                    input_payload={"order_id": "123", "total_amount": 99.99},
                    expected_output={"orderId": "123", "amount": 99.99},
                    description="Renames snake_case to camelCase",
                ),
            ],
        )

    def get_context_additions(self, transform_spec: dict[str, Any]) -> dict[str, Any]:
        """Inject field mappings into template context."""
        return {"field_mappings": transform_spec.get("config", {}).get("mappings", [])}


# ---------------------------------------------------------------------------
# JOLT
# ---------------------------------------------------------------------------


class JoltTransformEngine(TransformEngine):
    """JOLT JSON-to-JSON transformation."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="jolt",
            display_name="JOLT",
            description="JOLT JSON transformation spec.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/JoltTransform.java",
                    template_name="integration-java-mdk/transforms/JoltTransform.java.j2",
                ),
                TransformOutput(
                    relative_path="src/main/resources/transforms/jolt-spec.json",
                    template_name="integration-java-mdk/transforms/jolt-spec.json.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="shift_operation",
                    input_payload={"data": {"id": "123"}},
                    expected_output={"orderId": "123"},
                    description="JOLT shift extracts nested field",
                ),
            ],
        )

    def get_context_additions(self, transform_spec: dict[str, Any]) -> dict[str, Any]:
        return {"jolt_spec": transform_spec.get("config", {}).get("spec", "[]")}


# ---------------------------------------------------------------------------
# DataWeave
# ---------------------------------------------------------------------------


class DataWeaveTransformEngine(TransformEngine):
    """DataWeave transformation (rendered as .dwl module)."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="dataweave",
            display_name="DataWeave",
            description="MuleSoft DataWeave transformation language.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/DataWeaveTransform.java",
                    template_name="integration-java-mdk/transforms/DataWeaveTransform.java.j2",
                ),
                TransformOutput(
                    relative_path="src/main/resources/transforms/transform.dwl",
                    template_name="integration-java-mdk/transforms/transform.dwl.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="map_payload",
                    input_payload={"items": [{"name": "Widget", "qty": 3}]},
                    expected_output={"products": [{"productName": "Widget", "quantity": 3}]},
                    description="DataWeave maps array fields",
                ),
            ],
        )

    def get_context_additions(self, transform_spec: dict[str, Any]) -> dict[str, Any]:
        return {"dataweave_script": transform_spec.get("config", {}).get("script", "")}


# ---------------------------------------------------------------------------
# Scripting (JavaScript/Groovy/SpEL)
# ---------------------------------------------------------------------------


class ScriptingTransformEngine(TransformEngine):
    """Script-based transformation (JavaScript, Groovy, or SpEL)."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="scripting",
            display_name="Scripting",
            description="JavaScript, Groovy, or SpEL script transformation.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/ScriptTransform.java",
                    template_name="integration-java-mdk/transforms/ScriptTransform.java.j2",
                ),
                TransformOutput(
                    relative_path="src/main/resources/transforms/transform-script.js",
                    template_name="integration-java-mdk/transforms/transform-script.js.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="add_timestamp",
                    input_payload={"orderId": "123"},
                    expected_output={"orderId": "123", "processedAt": "2026-01-01T00:00:00Z"},
                    description="Script adds a timestamp field",
                ),
            ],
        )

    def get_context_additions(self, transform_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "script_language": transform_spec.get("config", {}).get("language", "javascript"),
            "script_content": transform_spec.get("config", {}).get("script", ""),
        }


# ---------------------------------------------------------------------------
# Custom Java
# ---------------------------------------------------------------------------


class CustomJavaTransformEngine(TransformEngine):
    """Custom Java transformation (user-implemented Function bean)."""

    def __init__(self) -> None:
        super().__init__(
            engine_id="custom_java",
            display_name="Custom Java",
            description="Custom Java Function bean for transformation.",
            outputs=[
                TransformOutput(
                    relative_path=f"{_BASE}/CustomTransform.java",
                    template_name="integration-java-mdk/transforms/CustomTransform.java.j2",
                ),
            ],
            fixtures=[
                TransformFixture(
                    name="custom_logic",
                    input_payload={"raw": "data"},
                    expected_output={"processed": "data"},
                    description="Custom Java transformation placeholder",
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_builtin_transforms() -> None:
    """Register all built-in transform engines."""
    register_transform(PassthroughTransformEngine())
    register_transform(FieldMappingTransformEngine())
    register_transform(JoltTransformEngine())
    register_transform(DataWeaveTransformEngine())
    register_transform(ScriptingTransformEngine())
    register_transform(CustomJavaTransformEngine())
