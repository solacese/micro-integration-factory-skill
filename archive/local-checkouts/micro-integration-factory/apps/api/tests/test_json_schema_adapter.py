from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec2event.adapters.source.json_schema_adapter import JsonSchemaSourceAdapter

API_ROOT = Path(__file__).resolve().parents[1]
ORDER_SCHEMA = API_ROOT / "resources" / "samples" / "json_schema" / "order.schema.json"


def test_parse_json_schema() -> None:
    adapter = JsonSchemaSourceAdapter()
    result = adapter.parse(ORDER_SCHEMA.read_text(encoding="utf-8"))
    assert result.document["title"] == "Order"
    assert "properties" in result.document


def test_parse_rejects_non_schema() -> None:
    adapter = JsonSchemaSourceAdapter()
    with pytest.raises(ValueError, match="Not a valid JSON Schema"):
        adapter.parse('{"name": "just a plain object"}')


def test_parse_rejects_non_object() -> None:
    adapter = JsonSchemaSourceAdapter()
    with pytest.raises(ValueError, match="must be a JSON object"):
        adapter.parse("[1, 2, 3]")


def test_summarize_json_schema() -> None:
    adapter = JsonSchemaSourceAdapter()
    doc = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
    summary = adapter.summarize(doc)
    assert summary.service_name == "order"
    assert summary.summary["title"] == "Order"
    assert summary.summary["propertyCount"] >= 1
    assert "serviceName" in summary.summary


def test_canonicalize_json_schema_produces_valid_model() -> None:
    adapter = JsonSchemaSourceAdapter()
    doc = json.loads(ORDER_SCHEMA.read_text(encoding="utf-8"))
    result = adapter.canonicalize(doc)
    cm = result.canonical_model

    assert cm["serviceName"] == "order"
    assert cm["title"] == "Order"
    assert cm["stripeEnabled"] is False
    assert len(cm["topics"]) >= 1
    assert len(cm["operations"]) >= 1
    assert len(cm["schemaNames"]) >= 1
    assert len(cm["applicationNames"]) >= 1
    assert cm["testFixtures"]


def test_canonicalize_generates_crud_operations() -> None:
    adapter = JsonSchemaSourceAdapter()
    doc = {
        "title": "Product",
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
            "price": {"type": "number"},
        },
    }
    result = adapter.canonicalize(doc)
    cm = result.canonical_model

    op_ids = [op["operationId"] for op in cm["operations"]]
    assert "createdProduct" in op_ids
    assert "updatedProduct" in op_ids
    assert "deletedProduct" in op_ids

    methods = {op["method"] for op in cm["operations"]}
    assert methods == {"POST", "PUT", "DELETE"}


def test_canonicalize_model_has_required_keys() -> None:
    """Verify the canonical model has the same top-level keys as the OpenAPI adapter."""
    adapter = JsonSchemaSourceAdapter()
    doc = {"title": "Widget", "type": "object", "properties": {"id": {"type": "string"}}}
    result = adapter.canonicalize(doc)
    cm = result.canonical_model

    required_keys = {
        "title",
        "serviceName",
        "serviceVersion",
        "servers",
        "authSchemes",
        "operations",
        "topics",
        "schemaNames",
        "applicationNames",
        "stripeEnabled",
        "testFixtures",
    }
    assert required_keys.issubset(cm.keys())


def test_canonicalize_with_definitions() -> None:
    """A schema with definitions should extract multiple entities."""
    adapter = JsonSchemaSourceAdapter()
    doc = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OrderSystem",
        "type": "object",
        "properties": {"id": {"type": "string"}},
        "definitions": {
            "LineItem": {
                "type": "object",
                "title": "LineItem",
                "properties": {"sku": {"type": "string"}, "qty": {"type": "integer"}},
            }
        },
    }
    result = adapter.canonicalize(doc)
    cm = result.canonical_model

    # Should have operations for both the root entity and LineItem
    op_ids = [op["operationId"] for op in cm["operations"]]
    assert any("ordersystem" in oid.lower() for oid in op_ids)
    assert any("lineitem" in oid.lower() for oid in op_ids)
