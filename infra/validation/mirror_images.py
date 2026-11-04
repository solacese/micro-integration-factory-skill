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
    metadata = json.loads(original.read_text()) if original.exists() else {}
    aliases = ["https://index.docker.io/v1/", "index.docker.io", "docker.io"]
    source_auth = None
    for alias in aliases:
        entry = metadata.get("auths", {}).get(alias, {})
        if entry.get("auth"):
            username, secret = base64.b64decode(entry["auth"]).decode().split(":", 1)
            source_auth = {"Username": username, "Secret": secret}
            break
        if entry.get("identitytoken"):
            source_auth = {"Username": "<token>", "Secret": entry["identitytoken"]}
            break
    with tempfile.TemporaryDirectory(prefix="mi-factory-registry-") as temporary:
        directory = Path(temporary)
        config = {"credHelpers": {registry: "mi-factory-ecr"}}
        if metadata.get("credsStore"):
            config["credsStore"] = metadata["credsStore"]
        for alias in aliases:
            if alias in metadata.get("credHelpers", {}):
                config["credHelpers"][alias] = metadata["credHelpers"][alias]
            elif source_auth:
                config["credHelpers"][alias] = "mi-factory-ecr"
        (directory / "config.json").write_text(json.dumps(config))
        executable = directory / "docker-credential-mi-factory-ecr"
        executable.write_text(
            '#!/usr/bin/env python3\nimport json,os,sys\nif sys.argv[1] != "get": sys.exit(1)\nserver=sys.stdin.read().strip()\nif server==os.environ["MI_FACTORY_ECR_REGISTRY"]: result={"Username":"AWS","Secret":os.environ["MI_FACTORY_ECR_TOKEN"]}\nelse: result=json.loads(os.environ["MI_FACTORY_SOURCE_AUTH"])\nif not result: sys.exit(1)\njson.dump(result,sys.stdout)\n'
        )
        executable.chmod(0o700)
        yield {
            **os.environ,
            "DOCKER_CONFIG": temporary,
            "PATH": temporary + os.pathsep + os.environ.get("PATH", ""),
            "MI_FACTORY_ECR_TOKEN": password,
            "MI_FACTORY_ECR_REGISTRY": registry,
            "MI_FACTORY_SOURCE_AUTH": json.dumps(source_auth),
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
            observed = subprocess.check_output(
                ["crane", "digest", images[source]], text=True, env=environment
            ).strip()
            if observed != digest:
                raise RuntimeError("Private registry content verification failed")
            print("Verified private worker image:", source, flush=True)
    return images, repo["repositoryArn"]
