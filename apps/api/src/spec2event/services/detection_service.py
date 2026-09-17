"""Source type auto-detection service.

Determines the appropriate source adapter based on:
1. File extension (strongest signal)
2. Content-type header (if provided)
3. Content sniffing (light heuristics, no full parsing)
4. Explicit override (always wins)
"""

from __future__ import annotations

import json
from typing import Any

import spec2event.adapters.source  # noqa: F401 (trigger registration)
from spec2event.adapters.source.registry import available_source_types


def detect_source_type(
    raw_content: str,
    filename: str | None = None,
    content_type: str | None = None,
    explicit_type: str | None = None,
) -> str:
    """Detect the source adapter type for the given content.

    Priority order:
    1. explicit_type (user override)
    2. File extension matching against registered adapters
    3. Content-type matching against registered adapters
    4. Content sniffing heuristics

    Returns the source_type string (e.g. "openapi", "json_schema", "database").
    Raises ValueError if detection fails.
    """
    # Priority 1: explicit override
    if explicit_type:
        if explicit_type in available_source_types():
            return explicit_type
        raise ValueError(
            f"Unknown source type: {explicit_type}. "
            f"Available: {available_source_types()}"
        )

    # Priority 2: file extension
    if filename:
        ext_type = _detect_by_extension(filename)
        if ext_type:
            return ext_type

    # Priority 3: content-type
    if content_type:
        ct_type = _detect_by_content_type(content_type)
        if ct_type:
            return ct_type

    # Priority 4: content sniffing
    sniffed_type = _detect_by_content(raw_content)
    if sniffed_type:
        return sniffed_type

    raise ValueError(
        "Could not auto-detect source type. "
        "Please specify source_type explicitly."
    )


def _detect_by_extension(filename: str) -> str | None:
    """Match filename extension against registered adapters."""
    lower = filename.lower()

    # OpenAPI specs
    if lower.endswith((".yaml", ".yml")):
        return "openapi"

    # JSON-based formats need content sniffing to differentiate
    if lower.endswith(".json"):
        return None  # Fall through to content sniffing

    if lower.endswith(".schema.json"):
        return "json_schema"

    return None


def _detect_by_content_type(content_type: str) -> str | None:
    """Match content-type against registered adapters."""
    ct = content_type.lower().split(";")[0].strip()
    if ct in ("application/yaml", "text/yaml", "application/x-yaml"):
        return "openapi"
    if ct == "application/schema+json":
        return "json_schema"
    return None


def _detect_by_content(raw_content: str) -> str | None:
    """Light content sniffing to detect source type.

    Does not fully parse the content, just looks for structural hints.
    """
    stripped = raw_content.strip()

    # YAML detection (OpenAPI)
    if stripped.startswith("openapi:") or "openapi:" in stripped[:200]:
        return "openapi"
    if stripped.startswith("swagger:") or "swagger:" in stripped[:200]:
        return "openapi"

    # JSON detection: try to identify specific formats
    if stripped.startswith("{"):
        try:
            doc = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return None

        if not isinstance(doc, dict):
            return None

        return _sniff_json_format(doc)

    return None


def _sniff_json_format(doc: dict[str, Any]) -> str | None:
    """Identify JSON document format by structural keys."""
    # OpenAPI (JSON format)
    if "openapi" in doc or "swagger" in doc:
        return "openapi"

    # JSON Schema
    if "$schema" in doc or (
        "type" in doc and "properties" in doc
    ):
        return "json_schema"

    # Integration spec (declarative intake)
    if "integration" in doc or (
        "input_system" in doc and "output_system" in doc
    ):
        return "integration_spec"

    # Database CDC spec
    if "tables" in doc and ("connection" in doc or "type" in doc):
        return "database"

    # Kafka/streaming spec
    if "topics" in doc and ("brokers" in doc or "bootstrap_servers" in doc):
        return "kafka"

    # Webhook spec
    if "endpoints" in doc or (
        "events" in doc and "signature_verification" in doc
    ):
        return "webhook"

    return None
