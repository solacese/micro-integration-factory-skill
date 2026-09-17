"""Shared utility functions for the spec2event services layer.

Extracted from openapi_service.py and json_schema_adapter.py to eliminate
duplication and provide a single source of truth for slug, pascal-case,
camel-case, singularization, and example generation helpers.
"""

from __future__ import annotations

import re
from typing import Any


def safe_slug(text: str) -> str:
    """Convert text to a URL/identifier-safe slug (lowercase, hyphens)."""
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return value or "generated-service"


def pascal(text: str) -> str:
    """Convert text to PascalCase."""
    parts = re.split(r"[^a-zA-Z0-9]+", text)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def camel(value: str) -> str:
    """Convert text to camelCase (first segment lowercase)."""
    cleaned = "".join(ch if ch.isalnum() else " " for ch in value).split()
    if not cleaned:
        return "generatedBinding"
    head, *tail = cleaned
    return head[:1].lower() + head[1:] + "".join(part[:1].upper() + part[1:] for part in tail)


def singularize(value: str) -> str:
    """Naive English singularization (handles common -s and -ies suffixes)."""
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value


def example_from_schema(schema: dict[str, Any] | None, depth: int = 0) -> Any:
    """Generate an example value from a JSON Schema definition.

    Recursively walks the schema up to a max depth, using ``example``,
    ``default``, and ``enum`` hints before falling back to type-based stubs.
    """
    if not schema or depth > 4:
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if schema_type == "object" or schema.get("properties"):
        properties = schema.get("properties") or {}
        return {key: example_from_schema(value, depth + 1) for key, value in properties.items()}
    if schema_type == "array":
        item_example = example_from_schema(schema.get("items"), depth + 1)
        return [] if item_example is None else [item_example]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        fmt = schema.get("format")
        if fmt == "date-time":
            return "2026-01-01T00:00:00Z"
        if fmt == "date":
            return "2026-01-01"
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        return schema.get("title") or "string"
    if "oneOf" in schema and schema["oneOf"]:
        return example_from_schema(schema["oneOf"][0], depth + 1)
    if "anyOf" in schema and schema["anyOf"]:
        return example_from_schema(schema["anyOf"][0], depth + 1)
    return None
