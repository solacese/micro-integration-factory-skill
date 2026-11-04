#!/usr/bin/env python3
"""Create a focused MI v1 from a Core.java specification, without an AI or cloud call."""

import argparse
import base64
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
from spec2event.services.core_project_service import create_core_project

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("spec", type=Path)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
result = create_core_project(json.loads(args.spec.read_text()))
content = base64.b64decode(result["zipBase64"])
archive = args.output / result["filename"]
archive.write_bytes(content)
with zipfile.ZipFile(io.BytesIO(content)) as z:
    z.extractall(args.output)
for p in args.output.rglob("*.sh"):
    p.chmod(0o755)
print(archive.resolve())
