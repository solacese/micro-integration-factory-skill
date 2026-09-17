from __future__ import annotations

from pathlib import Path

from spec2event.adapters.build.base import BuildEngine, BuildResult
from spec2event.services.aws_service import AwsService
from spec2event.services.command_runner import run_command, run_command_with_input


class EcrDockerBuildEngine(BuildEngine):
    def __init__(self, aws_service: AwsService | None = None) -> None:
        self.aws_service = aws_service or AwsService()

    def build(self, workspace_path: Path, image_tag: str) -> BuildResult:
        logs: list[str] = []
        try:
            auth = self.aws_service.ecr_auth()
        except Exception as exc:
            return BuildResult(status="not_configured", message=f"AWS/ECR auth failed: {exc}")

        login = run_command_with_input(
            [
                "docker",
                "login",
                auth.registry,
                "-u",
                "AWS",
                "--password-stdin",
            ],
            cwd=workspace_path,
            input_text=auth.password,
        )
        logs.extend(part for part in [login.stdout, login.stderr] if part)
        if login.returncode != 0:
            return BuildResult(
                status="failed",
                message="ECR docker login failed",
                logs="\n".join(logs),
            )

        build = run_command(
            ["docker", "build", "--platform", "linux/amd64", "-t", image_tag, "."],
            cwd=workspace_path,
        )
        logs.extend(part for part in [build.stdout, build.stderr] if part)
        if build.returncode != 0:
            return BuildResult(
                status="failed",
                message="Docker build failed",
                logs="\n".join(logs),
            )

        push = run_command(["docker", "push", image_tag], cwd=workspace_path)
        logs.extend(part for part in [push.stdout, push.stderr] if part)
        if push.returncode != 0:
            return BuildResult(
                status="failed",
                message="Docker push to ECR failed",
                logs="\n".join(logs),
            )

        return BuildResult(
            status="completed",
            message="Container image built and pushed to ECR",
            image_tag=image_tag,
            logs="\n".join(logs),
        )
