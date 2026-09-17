from __future__ import annotations

from spec2event.adapters.source.base import SourceAdapter

_REGISTRY: dict[str, type[SourceAdapter]] = {}


def register_source(source_type: str, adapter_cls: type[SourceAdapter]) -> None:
    _REGISTRY[source_type] = adapter_cls


def get_source_adapter(source_type: str) -> SourceAdapter:
    cls = _REGISTRY.get(source_type)
    if cls is None:
        available = sorted(_REGISTRY.keys())
        raise ValueError(f"Unknown source type: {source_type}. Available: {available}")
    return cls()


def available_source_types() -> list[str]:
    return sorted(_REGISTRY.keys())
