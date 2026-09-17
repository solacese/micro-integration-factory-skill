from __future__ import annotations

import pytest

import spec2event.adapters.source  # noqa: F401 -- trigger registration
from spec2event.adapters.source.registry import available_source_types, get_source_adapter


def test_openapi_registered() -> None:
    adapter = get_source_adapter("openapi")
    assert adapter.source_type == "openapi"


def test_json_schema_registered() -> None:
    adapter = get_source_adapter("json_schema")
    assert adapter.source_type == "json_schema"


def test_available_types_includes_both() -> None:
    types = available_source_types()
    assert "openapi" in types
    assert "json_schema" in types


def test_unknown_source_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown source type"):
        get_source_adapter("nonexistent")
