"""Scaffold a new transform engine.

Usage:
    python scripts/scaffold_transform.py --name xml_to_json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "spec2event"
TEMPLATES = ROOT / "resources" / "templates" / "integration-java-mdk" / "transforms"


def scaffold(name: str) -> None:
    pascal = "".join(part.capitalize() for part in name.split("_"))
    template_file = TEMPLATES / f"{pascal}Transform.java.j2"

    if template_file.exists():
        print(f"Template already exists: {template_file}")
        sys.exit(1)

    # Create Java template
    template_file.write_text(
        f'''package com.spec2event.generated.transform;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;

import java.util.function.Function;

/**
 * {pascal} transform for the {{{{ title }}}} micro-integration.
 *
 * TODO: Implement transformation logic.
 */
@Component("messageTransform")
public class {pascal}Transform implements Function<JsonNode, JsonNode> {{

    @Override
    public JsonNode apply(JsonNode input) {{
        // TODO: Implement {name} transformation
        return input;
    }}
}}
''',
        encoding="utf-8",
    )

    print(f"Scaffolded transform: {name}")
    print(f"  Template: {template_file}")
    print()
    print("Next steps:")
    print(f"  1. Add a {pascal}TransformEngine class in src/spec2event/transforms/engines.py")
    print("  2. Register it in register_builtin_transforms()")
    print("  3. Implement the transformation logic in the template")
    print("  4. Add golden fixtures to the engine class")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scaffold a new transform engine")
    parser.add_argument("--name", required=True, help="Transform name (e.g. xml_to_json)")
    args = parser.parse_args()
    scaffold(args.name)
