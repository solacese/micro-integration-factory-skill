"""Schema-to-typed-model generation service.

Generates Java POJOs/records from:
- OpenAPI component schemas
- JSON Schema definitions
- Avro schemas (planned)
- Protobuf definitions (planned)

The untyped JsonNode fallback remains the default. Typed models are
generated when schema definitions are available and the user opts in.
"""

from __future__ import annotations

import re
from typing import Any

from spec2event.services.utils import pascal as _pascal


def extract_models_from_canonical(
    canonical_model: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract typed model definitions from a canonical model.

    Scans operations for requestSchema/responseSchema and produces
    Java model descriptors suitable for template rendering.

    Returns a list of model descriptors, each with:
    - model_name: PascalCase Java class name
    - model_fields: list of field descriptors
    - model_imports: list of required Java imports
    """
    models: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for operation in canonical_model.get("operations", []):
        for schema_key in ("requestSchema", "responseSchema"):
            schema = operation.get(schema_key)
            if not schema or not isinstance(schema, dict):
                continue
            # Derive model name
            schema_name_key = schema_key.replace("Schema", "SchemaName")
            raw_name = operation.get(schema_name_key) or operation.get("operationId", "Model")
            model_name = _pascal(raw_name)
            if model_name in seen_names:
                continue
            seen_names.add(model_name)

            fields = _extract_fields(schema)
            if not fields:
                continue

            imports = _collect_imports(fields)
            models.append({
                "model_name": model_name,
                "model_fields": fields,
                "model_imports": sorted(imports),
            })

    return models


def _extract_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract field descriptors from a JSON Schema object."""
    properties = schema.get("properties", {})
    if not properties:
        return []

    fields: list[dict[str, Any]] = []
    for prop_name, prop_schema in properties.items():
        java_type = _json_type_to_java(prop_schema)
        java_name = _to_camel_case(prop_name)
        fields.append({
            "json_name": prop_name,
            "java_name": java_name,
            "java_type": java_type,
            "nullable": prop_name not in schema.get("required", []),
        })
    return fields


def _json_type_to_java(schema: dict[str, Any]) -> str:
    """Map a JSON Schema type to a Java type."""
    schema_type = schema.get("type", "object")
    fmt = schema.get("format", "")

    if schema_type == "string":
        if fmt == "date-time":
            return "java.time.Instant"
        if fmt == "date":
            return "java.time.LocalDate"
        if fmt == "uuid":
            return "java.util.UUID"
        return "String"
    if schema_type == "integer":
        if fmt == "int64":
            return "Long"
        return "Integer"
    if schema_type == "number":
        if fmt == "float":
            return "Float"
        return "Double"
    if schema_type == "boolean":
        return "Boolean"
    if schema_type == "array":
        items = schema.get("items", {})
        item_type = _json_type_to_java(items)
        return f"java.util.List<{item_type}>"
    if schema_type == "object":
        # Nested object - use JsonNode as fallback
        return "com.fasterxml.jackson.databind.JsonNode"
    return "Object"


def _collect_imports(fields: list[dict[str, Any]]) -> set[str]:
    """Collect Java imports needed for the field types."""
    imports: set[str] = set()
    for field in fields:
        java_type = field["java_type"]
        if java_type.startswith("java."):
            # Extract the base type for List<T>
            base = java_type.split("<")[0]
            imports.add(base)
            # Also import the generic type if it's a qualified name
            if "<" in java_type:
                inner = java_type.split("<")[1].rstrip(">")
                if "." in inner:
                    imports.add(inner)
        elif java_type == "com.fasterxml.jackson.databind.JsonNode":
            imports.add(java_type)
    return imports


def _to_camel_case(name: str) -> str:
    """Convert a property name to camelCase Java field name."""
    # Handle snake_case
    parts = re.split(r"[_\-\s]+", name)
    if not parts:
        return name
    return parts[0] + "".join(p.capitalize() for p in parts[1:])
