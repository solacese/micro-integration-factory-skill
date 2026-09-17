from __future__ import annotations

from pathlib import Path

from spec2event.adapters.deploy.base import DeploymentAdapter, DeployResult


class KubernetesHelmDeploymentAdapter(DeploymentAdapter):
    def deploy(
        self, workspace_path: Path, image_tag: str, runtime_env: dict[str, str], run_id: str
    ) -> DeployResult:
        del image_tag, runtime_env, run_id
        return DeployResult(
            status="not_configured",
            message=(
                "Kubernetes deployment is adapter-ready but not the first "
                "required end-to-end path."
            ),
            service_url=None,
            logs=str(workspace_path / "helm"),
        )
