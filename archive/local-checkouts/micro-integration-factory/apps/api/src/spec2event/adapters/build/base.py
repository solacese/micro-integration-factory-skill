from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class BuildResult:
    status: str
    message: str
    image_tag: str | None = None
    logs: str | None = None


class BuildEngine:
    def build(self, workspace_path: Path, image_tag: str) -> BuildResult:
        raise NotImplementedError
