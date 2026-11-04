"""Package one business-logic Java file with a fixed, tested MI runtime."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from spec2event.services.utils import safe_slug

TEMPLATES = Path(__file__).resolve().parents[3] / "resources/templates/core-java"
DEPENDENCIES = {
    "json_schema": ("com.networknt", "json-schema-validator", "3.0.8"),
    "avro": ("org.apache.avro", "avro", "1.12.2"),
    "protobuf": ("com.google.protobuf", "protobuf-java", "4.35.1"),
}


def create_core_project(spec: dict, sources: list[dict] | None = None) -> dict:
    if not (TEMPLATES / "pom.xml.j2").is_file():
        raise RuntimeError("The standard Java runtime templates are missing")
    name = safe_slug(str(spec.get("name", "my-mi")))[:64]
    core = str(spec.get("core_java", ""))
    if not 80 < len(core) < 45_000:
        raise ValueError("Provide a complete Core.java file, up to 45 KB")
    if not re.search(r"package\s+com\.solace\.mi\s*;", core):
        raise ValueError("Core.java must use package com.solace.mi")
    if not re.search(r"public\s+(?:final\s+)?class\s+Core\b", core):
        raise ValueError("Core.java must declare public class Core")
    if not re.search(r"public\s+byte\[\]\s+process\s*\(", core):
        raise ValueError(
            "Core.java needs public byte[] process(byte[] payload, Map<String,Object> headers)"
        )
    if re.search(r"\bTODO\b|YOUR_API_KEY|IMPLEMENT_ME|return\s+null\s*;", core):
        raise ValueError("Complete the core logic instead of returning a placeholder")
    chosen = spec.get("dependencies", [])
    if not isinstance(chosen, list) or any(key not in DEPENDENCIES for key in chosen):
        raise ValueError("Dependencies must be selected from json_schema, avro, protobuf")
    examples = spec.get("examples", [])
    if not isinstance(examples, list) or not 1 <= len(examples) <= 8:
        raise ValueError("Include one to eight executable input/output contract examples")
    for example in examples:
        if not isinstance(example, dict) or "input_base64" not in example:
            if isinstance(example, dict) and isinstance(example.get("input"), str):
                example["input_base64"] = base64.b64encode(example.pop("input").encode()).decode()
            else:
                raise ValueError("Each example needs input or input_base64")
        if isinstance(example.get("output"), str):
            example["output_base64"] = base64.b64encode(example.pop("output").encode()).decode()
        for key in ["input_base64", "output_base64"]:
            if key in example:
                decoded = base64.b64decode(example[key], validate=True)
                if len(decoded) > 100_000:
                    raise ValueError("Contract example is too large")
        if "output_base64" not in example and example.get("expected_error") is not True:
            raise ValueError("Each example needs output_base64 or expected_error=true")
        if not isinstance(example.get("headers", {}), dict):
            raise ValueError("Example headers must be an object")
        if "output_topics" in example:
            topics = example["output_topics"]
            if (
                not isinstance(topics, list)
                or not 1 <= len(topics) <= 16
                or any(
                    not isinstance(topic, str)
                    or len(topic) > 250
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", topic)
                    for topic in topics
                )
            ):
                raise ValueError("Example output_topics needs concrete Solace topic names")
    if not any("output_base64" in example for example in examples):
        raise ValueError(
            "Include at least one successful input/output example for the broker smoke test"
        )
    context = {
        "name": name,
        "description": str(spec.get("description", "Custom micro integration"))[:500],
        "dependencies": [DEPENDENCIES[key] for key in dict.fromkeys(chosen)],
        "webhook": spec.get("webhook", "none"),
    }
    if context["webhook"] not in {"none", "stripe"}:
        raise ValueError("webhook must be none or stripe")
    jinja = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    files = {}
    for path in sorted(TEMPLATES.rglob("*.j2")):
        relative = path.relative_to(TEMPLATES).as_posix()[:-3]
        files[relative] = jinja.get_template(path.relative_to(TEMPLATES).as_posix()).render(
            **context
        )
    required = {
        "pom.xml",
        "Dockerfile",
        ".env.example",
        "compose.yaml",
        "compose.demo.yaml",
        "scripts/install.sh",
        "scripts/verify.sh",
        "scripts/smoke.sh",
        "src/main/java/com/solace/mi/Application.java",
        "src/main/resources/application.yml",
    }
    if missing := required - files.keys():
        raise RuntimeError("The standard runtime is incomplete: " + ", ".join(sorted(missing)))
    files["src/main/java/com/solace/mi/Core.java"] = core.rstrip() + "\n"
    files["src/test/resources/core-examples.json"] = json.dumps(examples, indent=2)
    for variable in spec.get("required_env", []):
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,80}", variable):
            raise ValueError("Environment variable names must be uppercase identifiers")
        if not re.search(r"^" + variable + "=", files[".env.example"], re.M):
            files[".env.example"] += variable + "=replace-me\n"
    # Include provenance, never full third-party documents or credential material.
    evidence = [
        {k: v for k, v in source.items() if k in {"title", "url", "status", "fetchedAt", "sha256"}}
        for source in sources or []
    ]
    files["generation.json"] = json.dumps(
        {
            "name": name,
            "version": "1.0.0",
            "editableCore": "src/main/java/com/solace/mi/Core.java",
            "mdkVersion": "4.3.11",
            "javaRelease": 17,
            "webhook": context["webhook"],
            "contractExamples": len(examples),
            "verification": {
                "compile": "not_run",
                "contractTests": "not_run",
                "brokerRoundTrip": "not_run",
            },
            "assumptions": spec.get("assumptions", []),
            "sources": evidence,
        },
        indent=2,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, content in files.items():
            info = zipfile.ZipInfo(f"{name}-mi-v1/{relative}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if relative.endswith(".sh") else 0o100644) << 16
            archive.writestr(info, content)
    data = buffer.getvalue()
    return {
        "filename": f"{name}-mi-v1.zip",
        "zipBase64": base64.b64encode(data).decode(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "coreJava": core,
        "status": "generated",
        "contractExamples": len(examples),
        "files": len(files),
        "assumptions": spec.get("assumptions", []),
    }
