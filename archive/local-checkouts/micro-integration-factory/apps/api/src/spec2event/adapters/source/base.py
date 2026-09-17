from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceParseResult:
    """Result of parsing raw input into an intermediate document."""

    document: dict[str, Any]
    raw_content: str


@dataclass
class SourceSummary:
    """Human-readable summary of the source for UI preview."""

    service_name: str
    summary: dict[str, Any]


@dataclass
class SourceCanonicalResult:
    """The canonical model produced by canonicalization."""

    canonical_model: dict[str, Any]


class SourceAdapter:
    """Interface that every source type must implement.

    Subclasses override ``parse``, ``summarize``, and ``canonicalize`` to handle
    a specific input format (OpenAPI, JSON Schema, database credentials, etc.).
    All adapters must produce the same canonical model shape so that the
    downstream pipeline (generation, build, deploy, portal sync) remains generic.

    The canonical model returned by ``canonicalize`` must include an
    ``ingressType`` key that tells the generator which ingress adapter to
    render in the generated Solace MDK project.  Supported values:

    - ``rest_controller`` — HTTP REST endpoints (OpenAPI, JSON Schema)
    - ``polling_consumer`` — scheduled polling (database, file)
    - ``event_subscriber`` — stream consumer (MQTT, Kafka)
    """

    source_type: str = "unknown"
    accepted_extensions: list[str] = field(default_factory=list)
    accepted_content_types: list[str] = field(default_factory=list)

    def parse(self, raw_content: str) -> SourceParseResult:
        """Parse raw uploaded content into a structured document."""
        raise NotImplementedError

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        """Produce a human-readable summary for UI preview."""
        raise NotImplementedError

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        """Transform the parsed document into the canonical event model."""
        raise NotImplementedError
