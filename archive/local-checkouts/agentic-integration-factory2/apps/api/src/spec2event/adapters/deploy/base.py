from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class DeployResult:
    status: str
    message: str
    service_url: str | None = None
    logs: str | None = None
    metadata: dict[str, object] | None = None


class DeploymentAdapter:
    def deploy(
        self, workspace_path: Path, image_tag: str, runtime_env: dict[str, str], run_id: str
    ) -> DeployResult:
        raise NotImplementedError
