from __future__ import annotations

from typing import Any

from spec2event.adapters.source.base import (
    SourceAdapter,
    SourceCanonicalResult,
    SourceParseResult,
    SourceSummary,
)
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)


class OpenApiSourceAdapter(SourceAdapter):
    source_type = "openapi"
    accepted_extensions = [".yaml", ".yml", ".json"]
    accepted_content_types = ["application/yaml", "application/json", "text/yaml"]

    def parse(self, raw_content: str) -> SourceParseResult:
        document = load_openapi_document(raw_content)
        return SourceParseResult(document=document, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        summary = summarize_openapi(document)
        return SourceSummary(service_name=summary["serviceName"], summary=summary)

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        canonical = canonicalize_openapi(document)
        canonical.setdefault("ingressType", "rest_controller")
        return SourceCanonicalResult(canonical_model=canonical)
