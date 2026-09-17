from __future__ import annotations

from pathlib import Path

from spec2event.adapters.build.base import BuildEngine, BuildResult
from spec2event.services.command_runner import run_command, run_command_with_input


class LocalDockerBuildEngine(BuildEngine):
    def __init__(
        self,
        *,
        push: bool = False,
        registry: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.push = push
        self.registry = registry
        self.username = username
        self.password = password

    def build(self, workspace_path: Path, image_tag: str) -> BuildResult:
        logs: list[str] = []
        if self.push:
            if not self.registry or not self.username or not self.password:
                return BuildResult(
                    status="not_configured",
                    message="Registry credentials are required for remote image push",
                )
            login = run_command_with_input(
                [
                    "docker",
                    "login",
                    self.registry,
                    "-u",
                    self.username,
                    "--password-stdin",
                ],
                cwd=workspace_path,
                input_text=self.password,
            )
            logs.extend(part for part in [login.stdout, login.stderr] if part)
            if login.returncode != 0:
                return BuildResult(
                    status="failed",
                    message="Container registry login failed",
                    logs="\n".join(logs),
                )
            result = run_command(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--platform",
                    "linux/amd64",
                    "-t",
                    image_tag,
                    "--push",
                    ".",
                ],
                cwd=workspace_path,
            )
        else:
            result = run_command(["docker", "build", "-t", image_tag, "."], cwd=workspace_path)
        status = "completed" if result.returncode == 0 else "failed"
        message = (
            "Docker image built successfully"
            if result.returncode == 0 and not self.push
            else "Container image built and pushed successfully"
            if result.returncode == 0
            else "Docker build failed"
        )
        logs.extend(part for part in [result.stdout, result.stderr] if part)
        return BuildResult(
            status=status,
            message=message,
            image_tag=image_tag if result.returncode == 0 else None,
            logs="\n".join(logs),
        )
