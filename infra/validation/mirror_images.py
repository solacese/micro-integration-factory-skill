"""Mirror verified upstream Linux/amd64 bases into this factory's private ECR repository."""

from __future__ import annotations
import base64
import json
import shutil
import subprocess
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager

REPOSITORY = "mi-factory-validation/images"
SOURCES = {
    "go-bookworm": "golang:1.27.3-bookworm",
    "go-alpine": "golang:1.27.3-alpine",
    "debian": "debian:bookworm-slim",
    "maven": "maven:3.9.15-eclipse-temurin-17",
    "java": "eclipse-temurin:17-jre",
    "broker": "solace/solace-pubsub-standard:latest",
}


@contextmanager
def credential_environment(registry, password):
    original = (
        Path(os.getenv("DOCKER_CONFIG", str(Path.home() / ".docker"))) / "config.json"
    )
    metadata = json.loads(original.read_text())
    helper = metadata.get("credHelpers", {}).get(
        "https://index.docker.io/v1/"
    ) or metadata.get("credsStore")
    if not helper:
        raise RuntimeError(
            "A Docker credential helper is required; sign in through Docker Desktop"
        )
    with tempfile.TemporaryDirectory(prefix="mi-factory-registry-") as temporary:
        directory = Path(temporary)
        (directory / "config.json").write_text(
            json.dumps(
                {"credsStore": helper, "credHelpers": {registry: "mi-factory-ecr"}}
            )
        )
        executable = directory / "docker-credential-mi-factory-ecr"
        executable.write_text(
            '#!/usr/bin/env python3\nimport json,os,sys\nif sys.argv[1] != "get": sys.exit(1)\njson.dump({"Username":"AWS","Secret":os.environ["MI_FACTORY_ECR_TOKEN"]},sys.stdout)\n'
        )
        executable.chmod(0o700)
        yield {
            **os.environ,
            "DOCKER_CONFIG": temporary,
            "PATH": temporary + os.pathsep + os.environ.get("PATH", ""),
            "MI_FACTORY_ECR_TOKEN": password,
        }


def prepare(session):
    if not shutil.which("crane"):
        raise RuntimeError(
            "Install crane (brew install crane) to mirror worker images before deployment"
        )
    ecr = session.client("ecr")
    try:
        repo = ecr.describe_repositories(repositoryNames=[REPOSITORY])["repositories"][
            0
        ]
    except ecr.exceptions.RepositoryNotFoundException:
        repo = ecr.create_repository(
            repositoryName=REPOSITORY,
            imageTagMutability="IMMUTABLE",
            encryptionConfiguration={"encryptionType": "AES256"},
            tags=[{"Key": "Project", "Value": "micro-integration-factory-skill"}],
        )["repository"]
    registry = repo["repositoryUri"].split("/")[0]
    authorization = ecr.get_authorization_token()["authorizationData"][0]
    password = (
        base64.b64decode(authorization["authorizationToken"]).decode().split(":", 1)[1]
    )
    images = {}
    # Preserve the caller's Docker configuration and credentials; ECR auth stays in child memory.
    with credential_environment(registry, password) as environment:
        for name, source in SOURCES.items():
            digest = subprocess.check_output(
                ["crane", "digest", "--platform", "linux/amd64", source],
                text=True,
                env=environment,
            ).strip()
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise RuntimeError("Invalid upstream image digest")
            tag = name + "-" + digest.split(":")[1][:20]
            existing = ecr.batch_get_image(
                repositoryName=REPOSITORY, imageIds=[{"imageTag": tag}]
            )["images"]
            destination = repo["repositoryUri"] + ":" + tag
            if not existing:
                copied = subprocess.run(
                    [
                        "crane",
                        "copy",
                        "--platform",
                        "linux/amd64",
                        "--jobs",
                        "4",
                        source.split("@")[0] + "@" + digest,
                        destination,
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=900,
                    env=environment,
                )
                if copied.returncode:
                    raise RuntimeError(
                        "Image mirror copy failed for "
                        + source
                        + ": "
                        + copied.stdout[-1200:]
                    )
                existing = ecr.batch_get_image(
                    repositoryName=REPOSITORY, imageIds=[{"imageTag": tag}]
                )["images"]
            if not existing or existing[0]["imageId"]["imageDigest"] != digest:
                raise RuntimeError("The mirrored image digest does not match " + source)
            images[source] = repo["repositoryUri"] + "@" + digest
            print("Verified private worker image:", source, flush=True)
    return images, repo["repositoryArn"]
