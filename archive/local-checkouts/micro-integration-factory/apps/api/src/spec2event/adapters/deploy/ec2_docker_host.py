from __future__ import annotations

import shlex
import tempfile
from pathlib import Path

from spec2event.adapters.deploy.base import DeploymentAdapter, DeployResult
from spec2event.services.command_runner import run_command


class Ec2DockerHostDeploymentAdapter(DeploymentAdapter):
    def __init__(
        self,
        host: str,
        ssh_user: str,
        ssh_private_key: str,
        port: int,
        public_base_url: str | None = None,
    ) -> None:
        self.host = host
        self.ssh_user = ssh_user
        self.ssh_private_key = ssh_private_key
        self.port = port
        self.public_base_url = public_base_url

    def deploy(
        self, workspace_path: Path, image_tag: str, runtime_env: dict[str, str], run_id: str
    ) -> DeployResult:
        del run_id
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(self.ssh_private_key)
            handle.flush()
            key_path = Path(handle.name)
        key_path.chmod(0o600)
        env_exports = " ".join(
            f"-e {shlex.quote(key)}={shlex.quote(value)}" for key, value in runtime_env.items()
        )
        remote_container = image_tag.replace("/", "-").replace(":", "-")
        remote_command = (
            f"docker rm -f {shlex.quote(remote_container)} >/dev/null 2>&1 || true && "
            f"docker pull {shlex.quote(image_tag)} && "
            f"docker run -d --restart unless-stopped --name {shlex.quote(remote_container)} "
            f"-p 8080:8080 {env_exports} {shlex.quote(image_tag)}"
        )
        result = run_command(
            [
                "ssh",
                "-i",
                str(key_path),
                "-p",
                str(self.port),
                "-o",
                "StrictHostKeyChecking=no",
                f"{self.ssh_user}@{self.host}",
                remote_command,
            ],
            cwd=workspace_path,
        )
        logs = "\n".join(part for part in [result.stdout, result.stderr] if part)
        if result.returncode != 0:
            return DeployResult(status="failed", message="EC2 Docker deployment failed", logs=logs)
        service_url = self.public_base_url or f"http://{self.host}:8080"
        return DeployResult(
            status="completed",
            message="Deployed to EC2 Docker host",
            service_url=service_url,
            logs=logs,
        )
