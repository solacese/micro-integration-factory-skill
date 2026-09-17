from __future__ import annotations

import time
from pathlib import Path

from spec2event.adapters.deploy.base import DeploymentAdapter, DeployResult
from spec2event.config import get_settings
from spec2event.services.command_runner import run_command


class LocalDockerDeploymentAdapter(DeploymentAdapter):
    def deploy(
        self, workspace_path: Path, image_tag: str, runtime_env: dict[str, str], run_id: str
    ) -> DeployResult:
        del run_id
        settings = get_settings()
        container_name = image_tag.replace("/", "-").replace(":", "-")
        cleanup = run_command(["docker", "rm", "-f", container_name], cwd=workspace_path)
        env_args: list[str] = []
        for key, value in runtime_env.items():
            env_args.extend(["-e", f"{key}={value}"])
        deploy = run_command(
            [
                "docker",
                "run",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{settings.local_deploy_port}:8080",
                *env_args,
                image_tag,
            ],
            cwd=workspace_path,
        )
        logs = [
            part for part in [cleanup.stdout, cleanup.stderr, deploy.stdout, deploy.stderr] if part
        ]
        if deploy.returncode != 0:
            return DeployResult(
                status="failed",
                message="Local Docker deployment failed",
                logs="\n".join(logs),
            )
        time.sleep(3)
        running = run_command(
            ["docker", "ps", "-q", "--filter", f"name={container_name}"],
            cwd=workspace_path,
        )
        logs.extend(part for part in [running.stdout, running.stderr] if part)
        if not running.stdout.strip():
            container_logs = run_command(
                ["docker", "logs", "--tail", "200", container_name],
                cwd=workspace_path,
            )
            logs.extend(
                part for part in [container_logs.stdout, container_logs.stderr] if part
            )
            return DeployResult(
                status="failed",
                message="Local Docker container exited during startup",
                logs="\n".join(logs),
            )
        return DeployResult(
            status="completed",
            message="Deployed locally via Docker",
            service_url=f"http://localhost:{settings.local_deploy_port}",
            logs="\n".join(logs),
        )
