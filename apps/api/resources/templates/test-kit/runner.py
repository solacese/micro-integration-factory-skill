#!/usr/bin/env python3
"""Run generated MI examples, SDKPerf traffic, and the reproducible delivery benchmark."""

from __future__ import annotations
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import yaml
import uuid

ROOT = Path(__file__).resolve().parent


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def project_context(args):
    if not args.project:
        return None, None, None
    project = args.project.resolve()
    if not (project / "compose.yaml").is_file():
        raise ValueError("--project must be the unzipped Java or Go MI directory")
    compose = ["docker", "compose", "-f", "compose.yaml"]
    if args.demo:
        compose += ["-f", "compose.demo.yaml"]
    container = subprocess.check_output(
        [*compose, "ps", "-q", "integration"], cwd=project, text=True
    ).strip()
    if not container:
        raise ValueError("Start the MI with ./scripts/install.sh [--demo] first")
    state = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
    return project, compose, state


def config_path(args, project):
    return (
        args.config
        or (
            project / "config" / ("mi-demo.yaml" if args.demo else "mi-config.yaml")
            if project
            else ROOT / "config/mi-config.yaml"
        )
    ).resolve()


def endpoint(args, state, in_container=False):
    if args.url:
        return args.url
    if in_container and state:
        return "http://integration:8080/ingest"
    ports = (state or {}).get("NetworkSettings", {}).get("Ports", {}).get("8080/tcp")
    if ports:
        return "http://127.0.0.1:" + ports[0]["HostPort"] + "/ingest"
    return (
        "http://host.docker.internal:18080/ingest"
        if in_container
        else "http://127.0.0.1:18080/ingest"
    )


def http_samples(config, url, cases):
    stripe = config["webhook"]["provider"] == "stripe"
    key = config["webhook"].get("signing-secret", "")
    if stripe and (not key or key == "replace-me"):
        raise ValueError("Complete webhook.signing-secret in the shared YAML")

    def send(payload, headers):
        request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    for index, case in enumerate(cases):
        payload = base64.b64decode(case["input_base64"])
        headers = {
            "Content-Type": "application/json" if stripe else "application/octet-stream",
            **{str(k): str(v) for k, v in case.get("headers", {}).items()},
        }
        if stripe:
            assert send(payload, {}) == 422, "Unsigned webhook was accepted"
            stamp = str(int(time.time()))
            signature = hmac.new(
                key.encode(), stamp.encode() + b"." + payload, hashlib.sha256
            ).hexdigest()
            headers["Stripe-Signature"] = "t=" + stamp + ",v1=" + signature
        status = send(payload, headers)
        expected = 422 if case.get("expected_error") else 202
        if status != expected:
            raise AssertionError(f"Example {index + 1}: HTTP {status}, expected {expected}")
        print(f"PASS example {index + 1}: HTTP {status}")
    print(
        "HTTP status/signature checks passed. Use smoke for broker bytes/topics and performance for correlated delivery."
    )


def sdkperf(args, config, cases, state=None):
    if not args.sdkperf:
        raise ValueError(
            "Set --sdkperf to the installed JCSMP sdkperf_java.sh launcher; see README"
        )
    executable = Path(args.sdkperf).expanduser().resolve()
    if not executable.is_file():
        raise ValueError("SDKPerf launcher not found")
    example = next(case for case in cases if "output_base64" in case)
    if args.mode == "sdkperf-publish" and config["webhook"]["provider"] == "stripe":
        raise ValueError(
            "Stripe input requires signed HTTP. Run performance, with sdkperf-subscribe in another terminal."
        )
    topics = example.get("output_topics") or [config["messaging"]["output-topic"]]
    for topic in topics + [config["messaging"]["input-topic"]]:
        if "," in topic:
            raise ValueError("SDKPerf topic lists cannot contain commas")
    with tempfile.TemporaryDirectory(prefix="mi-sdkperf-") as temporary:
        password = Path(temporary) / "password"
        password.write_text(config["broker"]["password"])
        password.chmod(0o600)
        command = [
            str(executable),
            "-cip=" + config["broker"]["smf-url"],
            "-cu=" + config["broker"]["username"] + "@" + config["broker"]["vpn"],
            "-cpf=" + str(password),
            "-mt=persistent",
            "-cc=1",
            "-soe",
        ]
        if args.mode == "sdkperf-publish":
            payload = Path(temporary) / "input.bin"
            payload.write_bytes(base64.b64decode(example["input_base64"]))
            command += [
                "-ptl=" + config["messaging"]["input-topic"],
                "-pal=" + str(payload),
                "-mn=" + str(args.rate * args.seconds),
                "-mr=" + str(args.rate),
                "-ped=3",
            ]
            properties = []
            for key, value in example.get("headers", {}).items():
                kind = (
                    "Boolean"
                    if isinstance(value, bool)
                    else "Long"
                    if isinstance(value, int)
                    else "Double"
                    if isinstance(value, float)
                    else "String"
                )
                text = str(value).lower() if isinstance(value, bool) else str(value)
                if "," in str(key) + text or isinstance(value, (list, dict)):
                    raise ValueError("Use performance for complex example properties")
                properties += [kind, str(key), text]
            if properties:
                command += ["-cpl=" + ",".join(properties)]
        else:
            command += ["-stl=" + ",".join(topics), "-tte=1"]
        container = None
        if state:
            networks = list(state["NetworkSettings"]["Networks"])
            network = args.network or (networks[0] if len(networks) == 1 else None)
            if not network:
                raise ValueError("Specify --network for SDKPerf")
            container = "mi-sdkperf-" + uuid.uuid4().hex[:12]
            # Mount the user's own SDKPerf installation; no vendor binary is redistributed.
            rewritten = [
                argument.replace(str(password), "/fixture/password").replace(
                    str(Path(temporary) / "input.bin"), "/fixture/input.bin"
                )
                for argument in command[1:]
            ]
            command = [
                "docker",
                "run",
                "--rm",
                "--init",
                "-e",
                "TINI_KILL_PROCESS_GROUP=1",
                "--name",
                container,
                "--network",
                network,
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--read-only",
                "--tmpfs",
                "/tmp",
                "-v",
                str(executable.parent) + ":/sdkperf:ro",
                "-v",
                str(Path(temporary)) + ":/fixture:ro",
                "-w",
                "/sdkperf",
                "eclipse-temurin:17-jre",
                "bash",
                "/sdkperf/" + executable.name,
                *rewritten,
            ]
        output = ROOT / "results"
        output.mkdir(exist_ok=True)
        log = output / (args.mode + "-" + time.strftime("%Y%m%d-%H%M%S") + ".log")
        print("SDKPerf " + args.mode + "; raw payload preserved. Log: " + str(log), flush=True)
        with log.open("w") as stream:
            process = subprocess.Popen(
                command,
                cwd=executable.parent,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                try:
                    result = process.wait(
                        timeout=args.seconds + 15
                        if args.mode == "sdkperf-publish"
                        else args.seconds
                    )
                except subprocess.TimeoutExpired:
                    if args.mode == "sdkperf-publish":
                        raise RuntimeError(
                            "SDKPerf publisher did not finish its bounded message count"
                        )

                    if container:
                        subprocess.run(
                            ["docker", "kill", "--signal", "SIGINT", container],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        os.killpg(process.pid, signal.SIGINT)
                    result = process.wait(timeout=15)
                    if result in {0, 130, -signal.SIGINT}:
                        result = 0
                if result:
                    raise RuntimeError("SDKPerf failed; inspect " + str(log))
            finally:
                if container:
                    subprocess.run(
                        ["docker", "stop", "-t", "3", container],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
        print(
            "SDKPerf finished. Its traffic counters alone are not a verified MI delivery/latency result."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=[
            "verify",
            "smoke",
            "samples",
            "performance",
            "sdkperf-publish",
            "sdkperf-subscribe",
        ],
    )
    parser.add_argument("--project", type=Path)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--url")
    parser.add_argument("--sdkperf")
    parser.add_argument("--network")
    parser.add_argument("--transport", choices=["smf", "amqp"], default="amqp")
    parser.add_argument("--rate", type=int, default=1000)
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.rate <= 100000 or not 1 <= args.seconds <= 3600:
        parser.error("Use rate 1..100000 and seconds 1..3600")
    if args.mode in {"verify", "smoke"}:
        if not args.project:
            parser.error("--project is required")
        script = (
            args.project.resolve()
            / "scripts"
            / ("verify.sh" if args.mode == "verify" else "smoke.sh")
        )
        run([str(script)] + (["--demo"] if args.demo and args.mode == "smoke" else []))
        return
    project, compose, state = project_context(args)
    path = config_path(args, project)
    try:
        config = yaml.safe_load(path.read_text())
    except yaml.YAMLError:
        raise ValueError("Invalid shared YAML configuration") from None
    cases = json.loads((ROOT / "core-examples.json").read_text())
    if args.mode.startswith("sdkperf-"):
        sdkperf(args, config, cases, state)
        return
    if args.mode == "samples":
        http_samples(config, endpoint(args, state), cases)
        return
    run(["docker", "build", "-t", "mi-test-kit-loadtest:local", str(ROOT / "performance")])
    network = args.network
    if not network and state:
        networks = list(state["NetworkSettings"]["Networks"])
        if len(networks) != 1:
            raise ValueError("Specify --network when the MI belongs to multiple networks")
        network = networks[0]
    results = ROOT / "results" / time.strftime("%Y%m%d-%H%M%S")
    results.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--add-host",
        "host.docker.internal:host-gateway",
    ]
    if network:
        command += ["--network", network]
    command += [
        "-v",
        str(path) + ":/config.yaml:ro",
        "-v",
        str(ROOT / "core-examples.json") + ":/examples.json:ro",
        "-v",
        str(results) + ":/results",
        "mi-test-kit-loadtest:local",
        "-config",
        "/config.yaml",
        "-examples",
        "/examples.json",
        "-http",
        endpoint(args, state, True),
        "-transport",
        args.transport,
        "-rate",
        str(args.rate),
        "-seconds",
        str(args.seconds),
        "-warmup",
        "10",
        "-output",
        "/results/benchmark.json",
    ]
    run(command)
    report_file = results / "benchmark.json"
    report = json.loads(report_file.read_text())
    report["conditions"] = (
        ("local demo broker" if args.demo and project else "user-configured broker")
        + "; synthetic contract fixture; 2% input overdrive; all output topics verified; not maximum capacity"
    )
    report_file.write_text(json.dumps(report, indent=2))
    print("Verified benchmark and per-event CSV: " + str(results))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, AssertionError) as error:
        raise SystemExit(str(error))
