"""Transform engine registry and built-in engines."""

from spec2event.transforms.base import (
    TransformEngine,
    TransformFixture,
    TransformOutput,
    available_transform_engines,
    get_transform_engine,
    register_transform,
)
from spec2event.transforms.engines import register_builtin_transforms

# Auto-register built-in engines on import
register_builtin_transforms()

__all__ = [
    "TransformEngine",
    "TransformFixture",
    "TransformOutput",
    "available_transform_engines",
    "get_transform_engine",
    "register_transform",
]
