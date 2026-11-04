#!/usr/bin/env python3
"""Trusted build/load-test worker. Generated business code only executes inside containers."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parent


def run(command, cwd=None, timeout=600):
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            "Command failed: " + command[0] + "\n" + result.stdout[-5000:]
        )
    return result.stdout


def unpack(data: bytes, target: Path):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            path = Path(info.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Unsafe generated archive")
            if info.file_size > 10_000_000:
                raise ValueError("Generated file too large")
        archive.extractall(target)
        for info in archive.infolist():
            path = target / info.filename
            if path.is_file() and path.suffix == ".sh":
                path.chmod(0o755)
    directories = [path for path in target.iterdir() if path.is_dir()]
    if len(directories) != 1:
        raise ValueError("Expected one project root")
    return directories[0]


def configuration(project: dict):
    # Generated YAML has a fixed shape and JSON-quoted values; no arbitrary YAML tags are executed.
    document = {}
    section = None
    raw = base64.b64decode(project["configuration"]["zipBase64"]).decode()
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            section, value = line.split(":", 1)
            document[section] = {}
        elif section:
            key, value = line.strip().split(":", 1)
            # All scalar strings in the deterministic template are JSON quoted.
            decoded, _ = json.JSONDecoder().raw_decode(value.lstrip())
            document[section][key] = decoded
    document["broker"].update(
        {
            "smf-url": "tcp://broker:55555",
            "amqp-url": "amqp://broker:5672",
            "vpn": "default",
            "username": "default",
            "password": "default",
        }
    )
    if document["webhook"]["provider"] == "stripe":
        document["webhook"]["signing-secret"] = "whsec_isolated_fixture_only"
    return document


def _memory(value: str):
    match = re.match(r"([0-9.]+)([KMGT]?i?B)", value.strip())
    if not match:
        return 0
    scale = {
        "B": 1,
        "kB": 1000,
        "KB": 1000,
        "KiB": 1024,
        "MB": 1000**2,
        "MiB": 1024**2,
        "GB": 1000**3,
        "GiB": 1024**3,
    }
    return int(float(match[1]) * scale.get(match[2], 1))


def enrich_archive(original: bytes, report: dict, metrics: dict, csv: bytes):
    output = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(original)) as source,
        zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        root = Path(source.namelist()[0]).parts[0]
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("/generation.json"):
                metadata = json.loads(data)
                metadata["verification"] = {
                    "compile": "passed",
                    "contractTests": "passed",
                    "brokerRoundTrip": "passed",
                    "performance": "passed",
                }
                metadata["validation"] = metrics
                data = json.dumps(metadata, indent=2).encode()
            archive.writestr(info, data)
        for name, data in [
            ("validation.json", json.dumps(report, indent=2).encode()),
            ("benchmark.csv", csv),
        ]:
            info = zipfile.ZipInfo(root + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return output.getvalue()


def sandbox_network():
    # Containers never receive AWS variables, Docker socket mounts, or access to host metadata.
    run(["iptables", "-N", "MI_FACTORY_SANDBOX"]) if subprocess.run(
        ["iptables", "-L", "MI_FACTORY_SANDBOX"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode else None
    run(["iptables", "-F", "MI_FACTORY_SANDBOX"])
    rules = [
        ["-m", "conntrack", "--ctstate", "ESTABLISHED,RELATED", "-j", "RETURN"],
        ["-d", "172.28.42.1/32", "-j", "REJECT"],
        ["-d", "172.28.42.0/24", "-j", "RETURN"],
    ]
    for line in Path("/etc/resolv.conf").read_text().splitlines():
        if line.startswith("nameserver "):
            resolver = line.split()[1]
            if re.fullmatch(r"[0-9.]+", resolver):
                rules.extend(
                    [
                        ["-p", "udp", "-d", resolver, "--dport", "53", "-j", "RETURN"],
                        ["-p", "tcp", "-d", resolver, "--dport", "53", "-j", "RETURN"],
                    ]
                )
    rules.append(["-d", "169.254.0.0/16", "-j", "REJECT"])
    for network in ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]:
        rules.append(["-d", network, "-j", "REJECT"])
    rules.append(["-j", "RETURN"])
    for rule in rules:
        run(["iptables", "-A", "MI_FACTORY_SANDBOX", *rule])
    if subprocess.run(
        ["iptables", "-C", "DOCKER-USER", "-j", "MI_FACTORY_SANDBOX"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode:
        run(["iptables", "-I", "DOCKER-USER", "1", "-j", "MI_FACTORY_SANDBOX"])


def mirrored_dockerfile(directory):
    images = json.loads(os.getenv("VALIDATION_BASE_IMAGES", "{}"))
    if not images:
        return
    dockerfile = directory / "Dockerfile"
    lines = []
    for line in dockerfile.read_text().splitlines():
        if line.startswith("FROM "):
            prefix, source, *rest = line.split()
            if source.lower() != "scratch":
                if source not in images:
                    raise ValueError("Unapproved validation base image")
                line = " ".join([prefix, images[source], *rest])
        lines.append(line)
    dockerfile.write_text("\n".join(lines) + "\n")


def login_mirror():
    images = json.loads(os.getenv("VALIDATION_BASE_IMAGES", "{}"))
    if not images:
        return
    import boto3

    ecr = boto3.client("ecr")
    auth = ecr.get_authorization_token()["authorizationData"][0]
    username, password = (
        base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
    )
    registry = next(iter(images.values())).split("/")[0]
    result = subprocess.run(
        ["docker", "login", "--username", username, "--password-stdin", registry],
        input=password,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("Private worker image authentication failed")


def validate(project: dict, work: Path, progress=lambda *a: None):
    os.environ["MI_HTTP_PORT"] = "18190"
    report = {
        "status": "running",
        "targetRate": 1000,
        "durationSeconds": 10,
        "conditions": "isolated broker and synthetic contract fixtures; not live vendor capacity or maximum broker capacity",
        "environment": {
            "os": os.uname().sysname,
            "architecture": os.uname().machine,
            "cpuCount": os.cpu_count(),
            "compute": os.getenv("VALIDATION_COMPUTE", "local Docker host"),
            "baseImageDigests": {
                source: target.rsplit("@", 1)[1]
                for source, target in json.loads(
                    os.getenv("VALIDATION_BASE_IMAGES", "{}")
                ).items()
            },
            "runtimeCpuLimit": 2,
            "brokerCpuLimit": 4,
            "generatorCpuLimit": 2,
        },
        "runtimes": {},
    }
    progress("preparing", "Preparing isolated runtime validation")
    harness = "mi-factory-loadtest:validated"
    mirrored_dockerfile(ROOT / "loadtest")
    run(["docker", "build", "-t", harness, str(ROOT / "loadtest")], timeout=600)
    shared = configuration(project)
    artifacts = {}
    for language in ["java", "go"]:
        progress(language + "_build", "Building and testing " + language.upper())
        artifact = project[language]
        original = base64.b64decode(artifact["zipBase64"])
        directory = work / language
        directory.mkdir(parents=True)
        app = unpack(original, directory)
        mirrored_dockerfile(app)
        (app / ".env").write_text("MI_RUN_UID=65532\nMI_RUN_GID=65532\n")
        config_file = app / "config/mi-demo.yaml"
        config_file.write_text(json.dumps(shared, indent=2))
        config_file.chmod(0o644)  # synthetic fixture credentials only
        override = {
            "services": {
                "integration": {"user": "65532:65532", "cpus": 2},
                "broker": {"cpus": 4},
            },
            "networks": {
                "default": {"ipam": {"config": [{"subnet": "172.28.42.0/24"}]}}
            },
        }
        images = json.loads(os.getenv("VALIDATION_BASE_IMAGES", "{}"))
        if images:
            override["services"]["broker"]["image"] = images[
                "solace/solace-pubsub-standard:latest"
            ]
        (app / "compose.validation.json").write_text(json.dumps(override))
        compose = [
            "docker",
            "compose",
            "-p",
            "mi-validation",
            "-f",
            "compose.yaml",
            "-f",
            "compose.demo.yaml",
            "-f",
            "compose.validation.json",
        ]
        try:
            run([*compose, "up", "-d", "--wait", "broker"], app, 180)
            for suffix, data in [
                ("/clientUsernames/default", {"password": "default", "enabled": True}),
                ("", {"authenticationBasicType": "internal"}),
                (
                    "/clientProfiles/default",
                    {
                        "allowGuaranteedMsgSendEnabled": True,
                        "allowGuaranteedMsgReceiveEnabled": True,
                        "allowGuaranteedEndpointCreateEnabled": True,
                    },
                ),
            ]:
                run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "broker",
                        "curl",
                        "-fsS",
                        "-u",
                        "admin:admin",
                        "-X",
                        "PATCH",
                        "http://localhost:8080/SEMP/v2/config/msgVpns/default" + suffix,
                        "-H",
                        "Content-Type: application/json",
                        "-d",
                        json.dumps(data),
                    ],
                    app,
                    20,
                )
            run([*compose, "build", "integration"], app, 600)
            progress(
                language + "_start",
                "Starting " + language.upper() + " against the isolated broker",
            )
            run([*compose, "up", "-d", "--wait", "integration"], app, 180)
            container = run([*compose, "ps", "-q", "integration"], app).strip()
            image = run(
                ["docker", "inspect", "--format", "{{.Image}}", container]
            ).strip()
            image_bytes = int(
                run(
                    ["docker", "image", "inspect", "--format", "{{.Size}}", image]
                ).strip()
            )
            samples = []
            stop = threading.Event()

            def sample():
                while not stop.is_set():
                    try:
                        data = json.loads(
                            run(
                                [
                                    "docker",
                                    "stats",
                                    "--no-stream",
                                    "--format",
                                    "{{json .}}",
                                    container,
                                ],
                                timeout=10,
                            )
                        )
                        samples.append(
                            {
                                "memoryBytes": _memory(data["MemUsage"].split("/")[0]),
                                "cpuPercent": float(data["CPUPerc"].rstrip("%")),
                            }
                        )
                    except Exception:
                        pass
                    stop.wait(1)

            monitor = threading.Thread(target=sample, daemon=True)
            monitor.start()
            progress(
                language + "_performance",
                "Testing " + language.upper() + " at >=1,000 messages/s",
            )
            output = work / (language + "-performance")
            output.mkdir()
            output.chmod(0o777)
            examples = app / (
                "src/test/resources/core-examples.json"
                if language == "java"
                else "core-examples.json"
            )
            command = [
                "docker",
                "run",
                "--rm",
                "--network",
                "mi-validation_default",
                "--cpus",
                "2",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                str(config_file) + ":/config.yaml:ro",
                "-v",
                str(examples) + ":/examples.json:ro",
                "-v",
                str(output) + ":/results",
                harness,
                "-config",
                "/config.yaml",
                "-examples",
                "/examples.json",
                "-http",
                "http://integration:8080/ingest",
                "-output",
                "/results/benchmark.json",
                "-transport",
                "amqp",
                "-rate",
                "1000",
                "-seconds",
                "10",
                "-warmup",
                "10",
            ]
            failure = None
            try:
                run(command, timeout=90)
            except Exception as error:
                failure = error
            finally:
                stop.set()
                monitor.join(timeout=12)
            path = output / "benchmark.json"
            metrics = (
                json.loads(path.read_text())
                if path.exists()
                else {"passed": False, "error": "No complete benchmark report"}
            )
            metrics.update(
                imageBytes=image_bytes,
                sourceArchiveSha256=hashlib.sha256(original).hexdigest(),
                peakSampledMemoryBytes=max(
                    (s["memoryBytes"] for s in samples), default=0
                ),
                peakSampledCpuPercent=max(
                    (s["cpuPercent"] for s in samples), default=0
                ),
                resourceSamples=samples,
                transport="smf"
                if language == "java"
                else json.loads((app / "generation.json").read_text()).get(
                    "goTransport", "amqp"
                ),
            )
            report["runtimes"][language] = metrics
            if failure or not metrics.get("passed"):
                report["status"] = "failed"
                report["error"] = (
                    language.upper()
                    + " did not pass the 1,000 messages/s qualification"
                )
                continue
            artifacts[language] = {
                "original": original,
                "csv": (output / "benchmark.json.csv").read_bytes(),
            }
        except Exception as error:
            report.update(
                status="failed",
                error=language.upper() + " build/startup validation failed",
                diagnostic=str(error)[-4500:],
            )
        finally:
            try:
                (work / (language + "-runtime.log")).write_text(
                    run([*compose, "logs", "--tail", "300", "integration"], app, 20)
                )
            except Exception:
                pass
            try:
                run([*compose, "down", "--volumes", "--remove-orphans"], app, 60)
            except Exception:
                pass
    if len(artifacts) != 2:
        report["status"] = "failed"
        return report, {}
    report["status"] = "passed"
    finished = {
        language: enrich_archive(
            artifacts[language]["original"],
            report,
            report["runtimes"][language],
            artifacts[language]["csv"],
        )
        for language in ["java", "go"]
    }
    finished["configuration"] = base64.b64decode(project["configuration"]["zipBase64"])
    return report, finished


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/mi-validation"))
    args = parser.parse_args()
    bucket = os.getenv("VALIDATION_BUCKET")
    job = os.getenv("VALIDATION_JOB_ID")
    if args.local:
        project = json.loads(args.local.read_text())
        work = args.output.resolve()
        work.mkdir(parents=True, exist_ok=True)
        report, artifacts = validate(
            project, work, lambda stage, note: print(stage + ": " + note, flush=True)
        )
        (work / "report.json").write_text(json.dumps(report, indent=2))
        for language, data in artifacts.items():
            (
                work
                / (
                    "mi-config.yaml"
                    if language == "configuration"
                    else language + "-mi-v1.zip"
                )
            ).write_bytes(data)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "passed" else 1
    if not bucket or not job or not re.fullmatch(r"[a-f0-9]{32}", job):
        raise ValueError("Missing validation job")
    import boto3

    s3 = boto3.client("s3")
    prefix = "jobs/" + job + "/"
    raw = s3.get_object(Bucket=bucket, Key=prefix + "input.json")["Body"].read()
    request = json.loads(raw)
    work = Path("/tmp/mi-validation")
    work.mkdir(exist_ok=True)

    def progress(stage, note):
        s3.put_object(
            Bucket=bucket,
            Key=prefix + "progress.json",
            Body=json.dumps({"stage": stage, "note": note}).encode(),
            ContentType="application/json",
        )

    login_mirror()
    sandbox_network()
    try:
        report, artifacts = validate(request["project"], work, progress)
    except Exception as error:
        report, artifacts = (
            {
                "status": "failed",
                "error": "Validation worker failed",
                "diagnostic": str(error)[-3500:],
            },
            {},
        )
    report["inputSha256"] = hashlib.sha256(raw).hexdigest()
    report["jobId"] = job
    downloads = {}
    for language, data in artifacts.items():
        filename = request["project"][language]["filename"]
        key = prefix + "downloads/" + filename
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="application/yaml"
            if language == "configuration"
            else "application/zip",
        )
        downloads[language] = {
            "key": key,
            "filename": filename,
            "sha256": hashlib.sha256(data).hexdigest(),
            "contentType": "application/yaml"
            if language == "configuration"
            else "application/zip",
        }
    report["downloads"] = downloads
    s3.put_object(
        Bucket=bucket,
        Key=prefix + "report.json",
        Body=json.dumps(report).encode(),
        ContentType="application/json",
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
