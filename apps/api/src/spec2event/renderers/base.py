"""Base class and registry for binder renderers.

A binder renderer is responsible for generating the Java source files that
implement one side of a micro-integration workflow (either the source binder
or the target binder). Each renderer is keyed by (ingress/egress pattern,
direction) so that the generator service can look up the correct renderer
without if/elif branching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RenderOutput:
    """One file to write during generation."""

    relative_path: str  # Relative to workspace root
    template_name: str  # Jinja2 template path under templates_root


@dataclass
class BinderRenderer:
    """A binder renderer declares what files to generate for a given pattern.

    Subclass or instantiate directly to register renderers for specific
    (pattern, direction) combinations.
    """

    pattern: str  # e.g. "rest_controller", "polling_consumer", "event_subscriber"
    direction: str  # "source" or "target"
    binder_type: str  # Spring Cloud Stream binder type (e.g. "solace", "polling", "external")
    outputs: list[RenderOutput] = field(default_factory=list)

    def should_render(self, context: dict[str, Any]) -> bool:
        """Optional guard: return False to skip rendering (e.g. stripe-only files)."""
        return True

    def get_outputs(self, context: dict[str, Any]) -> list[RenderOutput]:
        """Return the list of files to render for this binder.

        Override for conditional logic (e.g. Stripe webhook controller only
        when stripe_enabled is True).
        """
        return [o for o in self.outputs if self.should_render(context)]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_RENDERER_REGISTRY: dict[tuple[str, str], BinderRenderer] = {}


def register_renderer(renderer: BinderRenderer) -> None:
    """Register a binder renderer by (pattern, direction) key."""
    key = (renderer.pattern, renderer.direction)
    _RENDERER_REGISTRY[key] = renderer


def get_renderer(pattern: str, direction: str) -> BinderRenderer | None:
    """Look up a renderer by pattern and direction. Returns None if not found."""
    return _RENDERER_REGISTRY.get((pattern, direction))


def available_renderers() -> list[tuple[str, str]]:
    """Return all registered (pattern, direction) keys."""
    return sorted(_RENDERER_REGISTRY.keys())
