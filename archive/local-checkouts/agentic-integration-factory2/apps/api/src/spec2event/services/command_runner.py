from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ALLOWED_COMMANDS = {"docker", "ssh", "bash", "mvn", "helm"}


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def run_command(args: Iterable[str], cwd: Path, env: dict[str, str] | None = None) -> CommandResult:
    return _run_command(args, cwd, env=env)


def _run_command(
    args: Iterable[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> CommandResult:
    command = list(args)
    if not command:
        raise ValueError("Missing command")
    if command[0] not in ALLOWED_COMMANDS:
        raise ValueError(f"Command {command[0]} is not allowlisted")
    process = subprocess.run(
        command,
        cwd=str(cwd),
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        input=input_text,
        check=False,
    )
    return CommandResult(
        args=command,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
    )


def run_command_with_input(
    args: Iterable[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    input_text: str,
) -> CommandResult:
    return _run_command(args, cwd, env=env, input_text=input_text)
