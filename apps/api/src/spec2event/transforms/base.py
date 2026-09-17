"""Base class and registry for transformation engines.

A transform engine generates the Java/config artifacts that implement the
message transformation step between the source binder and target binder
in a micro-integration workflow. Each engine is a pluggable, registry-driven
component that renders independently testable transform code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransformOutput:
    """One file produced by a transform engine."""

    relative_path: str  # Relative to workspace root
    template_name: str  # Jinja2 template path under templates_root


@dataclass
class TransformFixture:
    """Golden input/output test fixture for a transform."""

    name: str
    input_payload: dict[str, Any] | str
    expected_output: dict[str, Any] | str
    description: str = ""


@dataclass
class TransformEngine:
    """A transform engine renders the transform step in a workflow.

    Subclass or instantiate directly to register transform engines.
    The engine_id must match TransformEngine enum values in the contract.
    """

    engine_id: str  # passthrough, field_mapping, jolt, dataweave, scripting, custom_java
    display_name: str = ""
    description: str = ""
    outputs: list[TransformOutput] = field(default_factory=list)
    fixtures: list[TransformFixture] = field(default_factory=list)

    def get_outputs(self, context: dict[str, Any]) -> list[TransformOutput]:
        """Return the files to render for this transform engine."""
        return list(self.outputs)

    def get_context_additions(self, transform_spec: dict[str, Any]) -> dict[str, Any]:
        """Return additional context variables for template rendering.

        Override to inject engine-specific variables (mapping spec, JOLT spec, etc.).
        """
        return {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_TRANSFORM_REGISTRY: dict[str, TransformEngine] = {}


def register_transform(engine: TransformEngine) -> None:
    """Register a transform engine by engine_id."""
    _TRANSFORM_REGISTRY[engine.engine_id] = engine


def get_transform_engine(engine_id: str) -> TransformEngine | None:
    """Look up a transform engine by ID. Returns None if not found."""
    return _TRANSFORM_REGISTRY.get(engine_id)


def available_transform_engines() -> list[str]:
    """Return all registered engine IDs."""
    return sorted(_TRANSFORM_REGISTRY.keys())
