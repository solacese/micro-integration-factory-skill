#!/usr/bin/env python3
"""Create a focused MI v1 from a Core.java specification, without an AI or cloud call."""

import argparse
import base64
import io
import json
import sys
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
from spec2event.services.core_project_service import create_core_project
from spec2event.services.dual_project_service import create_dual_projects

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("spec", type=Path)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--go-transport",
    choices=["smf", "amqp"],
    help="Explicit Go wire protocol (otherwise use the designed spec)",
)
parser.add_argument(
    "--both", action="store_true", help="Package Java, Go, and shared YAML"
)
parser.add_argument(
    "--validate",
    action="store_true",
    help="Build both runtimes and require >=1,000 msg/s before writing downloads (Docker required)",
)
args = parser.parse_args()
if args.validate and not args.both:
    parser.error("--validate requires --both")
args.output.mkdir(parents=True, exist_ok=True)
spec = json.loads(args.spec.read_text())
if args.go_transport:
    spec["go_transport"] = args.go_transport
result = (create_dual_projects if args.both else create_core_project)(spec)
if args.validate:
    with tempfile.TemporaryDirectory(prefix="mi-factory-spec-") as temporary:
        source = Path(temporary) / "project.json"
        source.write_text(json.dumps(result))
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "infra/validation/worker.py"),
                "--local",
                str(source),
                "--output",
                str(args.output.resolve()),
            ],
            check=True,
        )
    sys.exit(0)
items = [result["java"], result["go"]] if args.both else [result]
for item in items:
    content = base64.b64decode(item["zipBase64"])
    archive = args.output / item["filename"]
    archive.write_bytes(content)
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        z.extractall(args.output)
    print(archive.resolve())
if args.both:
    configuration = args.output / result["configuration"]["filename"]
    configuration.write_bytes(base64.b64decode(result["configuration"]["zipBase64"]))
    print(configuration.resolve())
for p in args.output.rglob("*.sh"):
    p.chmod(0o755)
