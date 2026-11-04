"""Package equivalent Java and pure-Go MIs with one shared configuration file."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

GO_TEMPLATES = Path(__file__).resolve().parents[3] / "resources/templates/core-go"
GO_DEPENDENCIES = {
    "json_schema": ("github.com/santhosh-tekuri/jsonschema/v6", "v6.0.3"),
    "avro": ("github.com/linkedin/goavro/v2", "v2.15.0"),
    "protobuf": ("google.golang.org/protobuf", "v1.36.12"),
}


def shared_configuration(spec: dict, name: str) -> str:
    q = json.dumps
    variables = spec.get("required_env", [])
    if any(
        not isinstance(v, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", v) for v in variables
    ):
        raise ValueError("Environment variable names must be uppercase identifiers")
    return (
        f"""# One configuration file for either the Java or Go download.
# Save as config/mi-config.yaml in the project you run. Keep filled credentials private.
broker:
  smf-url: "tcp://host.docker.internal:55555" # Java / SMF
  amqp-url: "amqp://host.docker.internal:5672" # Go / AMQP 1.0; use this VPN's endpoint
  vpn: "default"
  username: "default"
  password: "replace-me"
messaging:
  input-topic: {q("mi/" + name + "/in")}
  output-topic: {q("mi/" + name + "/out")}
  subscription: {q(name)}
  error-topic: {q("mi/" + name + "/error")}
webhook:
  provider: {q(spec.get("webhook", "none"))}
  signing-secret: {q("replace-me" if spec.get("webhook") == "stripe" else "")}
credentials:"""
        + (
            "\n" + "\n".join("  " + key + ': "replace-me"' for key in dict.fromkeys(variables))
            if variables
            else " {}"
        )
        + "\n"
    )


def artifact(filename: str, data: bytes, **extra) -> dict:
    return {
        "filename": filename,
        "zipBase64": base64.b64encode(data).decode(),
        "sha256": hashlib.sha256(data).hexdigest(),
        **extra,
    }


def create_dual_projects(spec: dict, sources=None, service_plan=None) -> dict:
    # Import lazily: the Java packager also uses the shared config helper.
    from spec2event.services.core_project_service import create_core_project

    java = create_core_project(spec, sources, service_plan)
    transport = spec.get("go_transport", "amqp")
    if transport not in {"amqp", "smf"}:
        raise ValueError("go_transport must be amqp or smf")
    core = str(spec.get("core_go", ""))
    if not 80 < len(core) < 45_000 or not re.search(r"\bpackage\s+main\b", core):
        raise ValueError("Provide complete core_go using package main, up to 45 KB")
    if not re.search(r"func\s+Process\s*\(", core) or re.search(
        r"\bTODO\b|IMPLEMENT_ME|return\s+nil\s*,\s*nil\b", core
    ):
        raise ValueError(
            "Go needs a complete Process(payload []byte, headers map[string]any) ([]byte, error), without stubs"
        )
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(java["zipBase64"]))) as archive:
        report_path = next(p for p in archive.namelist() if p.endswith("/generation.json"))
        report = json.loads(archive.read(report_path))
        examples_path = next(
            p for p in archive.namelist() if p.endswith("/src/test/resources/core-examples.json")
        )
        examples = archive.read(examples_path).decode()
    name = report["name"]
    config = shared_configuration(spec, name)
    context = {
        "name": name,
        "description": str(spec.get("description", "Custom MI"))[:500],
        "webhook": spec.get("webhook", "none"),
        "transport": transport,
        "dependencies": [
            GO_DEPENDENCIES[key] for key in dict.fromkeys(spec.get("dependencies", []))
        ],
    }
    jinja = Environment(
        loader=FileSystemLoader(str(GO_TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    files = {
        p.relative_to(GO_TEMPLATES).as_posix()[:-3]: (
            p.read_text()
            if p.name.endswith(".go.j2")
            else jinja.get_template(p.relative_to(GO_TEMPLATES).as_posix()).render(**context)
        )
        for p in sorted(GO_TEMPLATES.rglob("*.j2"))
    }
    files.pop("transport_" + ("smf" if transport == "amqp" else "amqp") + ".go")
    smf_docker = files.pop("Dockerfile.smf")
    if transport == "smf":
        files["Dockerfile"] = smf_docker
    required = {
        "go.mod",
        "main.go",
        "config.go",
        "transport.go",
        "http.go",
        "core_test.go",
        "broker_test.go",
        "Dockerfile",
        "compose.yaml",
        "compose.demo.yaml",
        "scripts/install.sh",
        "scripts/smoke.sh",
    }
    if required - files.keys():
        raise RuntimeError("The standard Go runtime templates are incomplete")
    files.update(
        {
            "core.go": core.rstrip() + "\n",
            "transport_profile.go": "package main\nconst wireProtocol = "
            + json.dumps(transport)
            + "\n",
            "core-examples.json": examples,
            "config/mi-config.yaml": config,
        }
    )
    report.update(
        editableCore="core.go",
        runtime="Go / " + transport.upper(),
        goTransport=transport,
        goMinimum="1.26",
        goBuild="1.27.3",
    )
    report.pop("mdkVersion", None)
    report.pop("javaRelease", None)
    files["generation.json"] = json.dumps(report, indent=2)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            info = zipfile.ZipInfo(f"{name}-go-mi-v1/{path}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.endswith(".sh") else 0o100644) << 16
            archive.writestr(info, content)
    go = artifact(f"{name}-go-mi-v1.zip", buffer.getvalue(), coreGo=core, files=len(files))
    configuration = artifact("mi-config.yaml", config.encode(), contentType="application/yaml")
    return {**java, "java": java, "go": go, "configuration": configuration, "coreGo": core}
