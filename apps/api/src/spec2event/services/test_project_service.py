"""Package the generated contract examples and reproducible performance tooling."""

from __future__ import annotations
import base64
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[5]
TEMPLATES = ROOT / "apps/api/resources/templates/test-kit"
HARNESS = ROOT / "infra/validation/loadtest"


def create_test_project(project):
    from spec2event.services.dual_project_service import artifact

    files = {
        path.relative_to(TEMPLATES).as_posix(): path.read_bytes()
        for path in sorted(TEMPLATES.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    }
    for path in sorted(HARNESS.iterdir()):
        if path.name in {"Dockerfile", "go.mod", "go.sum", "main.go", "broker.go", "main_test.go"}:
            files["performance/" + path.name] = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(project["java"]["zipBase64"]))) as archive:
        root = archive.namelist()[0].split("/")[0]
        examples = archive.read(root + "/src/test/resources/core-examples.json")
        metadata = json.loads(archive.read(root + "/generation.json"))
    cases = json.loads(examples)
    files["core-examples.json"] = examples
    files["config/mi-config.yaml"] = base64.b64decode(project["configuration"]["zipBase64"])
    manifest = {
        "name": metadata["name"],
        "webhook": metadata.get("webhook", "none"),
        "examples": [],
        "commands": [
            "verify",
            "smoke",
            "samples",
            "performance",
            "sdkperf-publish",
            "sdkperf-subscribe",
        ],
        "sdkPerf": {
            "flavor": "JCSMP",
            "binaryIncluded": False,
            "execution": "not_run",
            "optionsReference": "https://docs.solace.com/API/SDKPerf/Command-Line-Options.htm",
        },
        "verification": "not_run",
    }
    for index, case in enumerate(cases, 1):
        prefix = f"fixtures/{index:02d}-" + ("invalid" if case.get("expected_error") else "valid")
        files[prefix + ".input.bin"] = base64.b64decode(case["input_base64"])
        if "output_base64" in case:
            files[prefix + ".expected.bin"] = base64.b64decode(case["output_base64"])
        manifest["examples"].append(
            {
                "input": prefix + ".input.bin",
                "expectedError": bool(case.get("expected_error")),
                "outputTopics": case.get("output_topics", []),
                "headers": case.get("headers", {}),
            }
        )
    for language in ["java", "go"]:
        with zipfile.ZipFile(
            io.BytesIO(base64.b64decode(project[language]["zipBase64"]))
        ) as archive:
            for name in archive.namelist():
                relative = "/".join(Path(name).parts[1:])
                if (language == "java" and relative.startswith("src/test/")) or (
                    language == "go" and relative.endswith("_test.go")
                ):
                    files["generated-tests/" + language + "/" + relative] = archive.read(name)
    files["test-manifest.json"] = json.dumps(manifest, indent=2).encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(
                metadata["name"] + "-tests/" + path, date_time=(2026, 1, 1, 0, 0, 0)
            )
            info.external_attr = (0o100755 if path.endswith(".sh") else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return artifact(
        metadata["name"] + "-tests.zip", output.getvalue(), contentType="application/zip"
    )
