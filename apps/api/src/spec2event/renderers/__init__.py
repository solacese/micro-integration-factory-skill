"""Binder renderer registry and built-in renderers."""

from spec2event.renderers.base import (
    BinderRenderer,
    RenderOutput,
    available_renderers,
    get_renderer,
    register_renderer,
)
from spec2event.renderers.source_renderers import register_builtin_source_renderers
from spec2event.renderers.target_renderers import register_builtin_target_renderers

# Auto-register built-in renderers on import
register_builtin_source_renderers()
register_builtin_target_renderers()

__all__ = [
    "BinderRenderer",
    "RenderOutput",
    "available_renderers",
    "get_renderer",
    "register_renderer",
]
