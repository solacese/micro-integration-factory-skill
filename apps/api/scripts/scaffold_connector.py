"""Scaffold a new connector (source adapter + renderer + sample + test).

Usage:
    python scripts/scaffold_connector.py --name mqtt --direction source
    python scripts/scaffold_connector.py --name s3 --direction both
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "spec2event"
TESTS = ROOT / "tests"
SAMPLES = ROOT / "resources" / "samples"


def scaffold(name: str, direction: str) -> None:
    adapter_file = SRC / "adapters" / "source" / f"{name}_adapter.py"
    sample_dir = SAMPLES / name
    test_file = TESTS / f"test_{name}_adapter.py"

    if adapter_file.exists():
        print(f"Adapter already exists: {adapter_file}")
        sys.exit(1)

    # Create adapter file
    adapter_file.write_text(
        f'''"""{ name.replace("_", " ").title() } source adapter.

TODO: Implement parse, summarize, canonicalize for the {name} connector.
"""

from __future__ import annotations

import json
from typing import Any

from spec2event.adapters.source.base import (
    SourceAdapter,
    SourceCanonicalResult,
    SourceParseResult,
    SourceSummary,
)
from spec2event.services.utils import pascal as _pascal
from spec2event.services.utils import safe_slug as _safe_slug


class {_pascal_name(name)}SourceAdapter(SourceAdapter):
    source_type = "{name}"
    accepted_extensions = [".json"]
    accepted_content_types = ["application/json"]

    def parse(self, raw_content: str) -> SourceParseResult:
        doc = json.loads(raw_content)
        if not isinstance(doc, dict):
            raise ValueError("{name} spec must be a JSON object")
        return SourceParseResult(document=doc, raw_content=raw_content)

    def summarize(self, document: dict[str, Any]) -> SourceSummary:
        service_name = _safe_slug(document.get("name", "{name}-source"))
        return SourceSummary(
            service_name=service_name,
            summary={{
                "title": document.get("name", "{name.title()} Source"),
                "serviceName": service_name,
            }},
        )

    def canonicalize(self, document: dict[str, Any]) -> SourceCanonicalResult:
        service_name = _safe_slug(document.get("name", "{name}-source"))
        application_name = f"{{service_name}}-integration"

        # TODO: Build operations, topics, schemas from document
        return SourceCanonicalResult(
            canonical_model={{
                "title": document.get("name", "{name.title()} Source"),
                "serviceName": service_name,
                "serviceVersion": "1.0.0",
                "servers": [],
                "authSchemes": [],
                "operations": [],
                "topics": [],
                "schemaNames": [],
                "applicationNames": [application_name],
                "stripeEnabled": False,
                "testFixtures": [],
                "ingressType": "event_subscriber",
                "direction": "{direction}",
            }}
        )
''',
        encoding="utf-8",
    )

    # Create sample directory and file
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_file = sample_dir / f"example-{name}.json"
    sample_file.write_text(
        f'{{\n  "name": "example-{name}",\n  "TODO": "Add {name}-specific configuration"\n}}\n',
        encoding="utf-8",
    )

    # Create test file
    test_file.write_text(
        f'''"""Tests for the {name} source adapter."""

from __future__ import annotations

from pathlib import Path

import spec2event.adapters.source  # noqa: F401
from spec2event.adapters.source.registry import get_source_adapter

API_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = API_ROOT / "resources" / "samples" / "{name}" / "example-{name}.json"


def test_{name}_adapter_parse() -> None:
    adapter = get_source_adapter("{name}")
    result = adapter.parse(SAMPLE.read_text())
    assert result.document is not None


def test_{name}_adapter_summarize() -> None:
    adapter = get_source_adapter("{name}")
    parsed = adapter.parse(SAMPLE.read_text())
    summary = adapter.summarize(parsed.document)
    assert summary.service_name
''',
        encoding="utf-8",
    )

    # Print registration instruction
    print(f"Scaffolded connector: {name}")
    print(f"  Adapter:  {adapter_file}")
    print(f"  Sample:   {sample_file}")
    print(f"  Test:     {test_file}")
    print()
    print("Next steps:")
    print("  1. Register in src/spec2event/adapters/source/__init__.py:")
    cls = _pascal_name(name)
    print(f"     from spec2event.adapters.source.{name}_adapter import {cls}SourceAdapter")
    print(f'     register_source("{name}", {_pascal_name(name)}SourceAdapter)')
    print(f"  2. Implement parse/summarize/canonicalize in {adapter_file.name}")
    print(f"  3. Update the sample input in {sample_file}")
    print(f"  4. Run: uv run pytest tests/test_{name}_adapter.py")


def _pascal_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scaffold a new connector")
    parser.add_argument("--name", required=True, help="Connector name (e.g. mqtt, s3)")
    parser.add_argument(
        "--direction",
        default="source",
        choices=["source", "target", "both"],
        help="Direction capability",
    )
    args = parser.parse_args()
    scaffold(args.name, args.direction)
