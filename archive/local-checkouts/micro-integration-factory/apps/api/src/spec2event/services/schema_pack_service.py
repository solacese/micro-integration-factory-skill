from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

import yaml
from fastapi import HTTPException
from sqlalchemy.orm import Session

from spec2event.models import SchemaPack
from spec2event.services.run_service import iso

MAX_PROMPT_RAW_EXCERPT = 1600


def create_schema_pack(
    db: Session,
    *,
    name: str,
    schema_format: str,
    raw_content: str,
    version: str | None = None,
    message_type: str | None = None,
    industry: str | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> SchemaPack:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="Schema pack name is required")
    normalized_format = schema_format.strip().lower()
    if not normalized_format:
        raise HTTPException(status_code=400, detail="Schema pack format is required")
    if not raw_content.strip():
        raise HTTPException(status_code=400, detail="Schema pack content is required")
    summary = summarize_schema_pack(
        raw_content,
        schema_format=normalized_format,
        version=version,
        message_type=message_type,
        industry=industry,
    )
    pack = SchemaPack(
        name=normalized_name,
        schema_format=normalized_format,
        version=_clean(version) or summary.get("version"),
        message_type=_clean(message_type) or summary.get("messageType"),
        industry=_clean(industry),
        filename=_clean(filename),
        content_type=_clean(content_type),
        raw_content=raw_content,
        summary_json=summary,
    )
    db.add(pack)
    db.flush()
    return pack


def list_schema_packs(db: Session) -> list[SchemaPack]:
    return db.query(SchemaPack).order_by(SchemaPack.created_at.desc()).all()


def get_schema_pack(db: Session, schema_pack_id: str) -> SchemaPack:
    pack = db.get(SchemaPack, schema_pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Schema pack not found")
    return pack


def delete_schema_pack(db: Session, schema_pack_id: str) -> None:
    pack = get_schema_pack(db, schema_pack_id)
    db.delete(pack)
    db.flush()


def serialize_schema_pack(pack: SchemaPack, *, include_raw: bool) -> dict[str, Any]:
    payload = {
        "id": pack.id,
        "name": pack.name,
        "schema_format": pack.schema_format,
        "version": pack.version,
        "message_type": pack.message_type,
        "industry": pack.industry,
        "filename": pack.filename,
        "summary": pack.summary_json or {},
        "created_at": iso(pack.created_at),
        "updated_at": iso(pack.updated_at),
    }
    if include_raw:
        payload["raw_content"] = pack.raw_content
    return payload


def schema_pack_prompt_context(pack: SchemaPack) -> dict[str, Any]:
    summary = pack.summary_json or {}
    return {
        "id": pack.id,
        "name": pack.name,
        "format": pack.schema_format,
        "version": pack.version,
        "messageType": pack.message_type,
        "industry": pack.industry,
        "counts": summary.get("counts") or {},
        "exampleMessageType": summary.get("exampleMessageType"),
        "messageTypes": _limit(summary.get("messageTypes"), 8),
        "structures": _limit(summary.get("structures"), 5),
        "segments": _limit(summary.get("segments"), 12),
        "composites": _limit(summary.get("composites"), 8),
        "fields": _limit(summary.get("fields"), 24),
        "requiredHints": _limit(summary.get("requiredHints"), 16),
        "repeatingHints": _limit(summary.get("repeatingHints"), 16),
        "mappingGuidance": (
            "Use this schema pack as the source or target structural contract. "
            "For HL7/EDI/XML cases, name the segment/structure/field mappings in "
            "validationNotes and implement a DataWeave-friendly mapping by default."
        ),
        "rawExcerpt": _truncate(pack.raw_content, MAX_PROMPT_RAW_EXCERPT),
    }


def summarize_schema_pack(
    raw_content: str,
    *,
    schema_format: str,
    version: str | None = None,
    message_type: str | None = None,
    industry: str | None = None,
) -> dict[str, Any]:
    normalized_format = schema_format.strip().lower()
    parsed = _parse_structured_content(raw_content, normalized_format)
    if normalized_format in {"hl7", "generic_edi", "edifact", "odette", "ansi_x12"}:
        summary = _summarize_hl7_or_edi(parsed, raw_content)
    elif normalized_format == "json_schema":
        summary = _summarize_json_schema(parsed, raw_content)
    elif normalized_format == "xml_schema":
        summary = _summarize_xml_schema(raw_content)
    elif normalized_format in {"csv_layout", "fixed_width"}:
        summary = _summarize_delimited_or_fixed_width(parsed, raw_content, normalized_format)
    else:
        summary = _summarize_text(raw_content)
    summary["format"] = normalized_format
    if version or summary.get("version"):
        summary["version"] = _clean(version) or summary.get("version")
    if message_type or summary.get("messageType"):
        summary["messageType"] = _clean(message_type) or summary.get("messageType")
    if industry:
        summary["industry"] = _clean(industry)
    return summary


def _summarize_hl7_or_edi(parsed: Any, raw_content: str) -> dict[str, Any]:
    document = parsed if isinstance(parsed, dict) else {}
    structures = _as_dict_list(document.get("structures"))
    segments = _as_dict_list(document.get("segments"))
    composites = _as_dict_list(document.get("composites"))
    version = _string(document.get("version"))
    message_types = [
        item
        for item in (_string(structure.get("id")) for structure in structures)
        if item is not None
    ]
    required_hints: list[str] = []
    repeating_hints: list[str] = []
    structure_summaries: list[dict[str, Any]] = []
    segment_summaries: list[dict[str, Any]] = []
    composite_summaries: list[dict[str, Any]] = []

    for structure in structures:
        items = _as_dict_list(structure.get("data"))
        flat_items = _flatten_schema_items(items)
        required_hints.extend(_required_hints(flat_items, _string(structure.get("id"))))
        repeating_hints.extend(_repeating_hints(flat_items, _string(structure.get("id"))))
        structure_summaries.append(
            {
                "id": _string(structure.get("id")),
                "name": _string(structure.get("name")),
                "itemCount": len(flat_items),
                "topItems": [
                    _schema_item_label(item)
                    for item in flat_items
                    if _schema_item_label(item) is not None
                ][:10],
            }
        )

    field_count = 0
    for segment in segments:
        values = _as_dict_list(segment.get("values"))
        field_count += len(values)
        segment_id = _string(segment.get("id")) or _string(segment.get("varTag"))
        required_hints.extend(_required_hints(values, segment_id))
        repeating_hints.extend(_repeating_hints(values, segment_id))
        segment_summaries.append(
            {
                "id": segment_id,
                "name": _string(segment.get("name")),
                "fieldCount": len(values),
                "fields": [_schema_item_label(value) for value in values[:12]],
            }
        )

    for composite in composites:
        values = _as_dict_list(composite.get("values"))
        field_count += len(values)
        composite_id = _string(composite.get("id"))
        required_hints.extend(_required_hints(values, composite_id))
        repeating_hints.extend(_repeating_hints(values, composite_id))
        composite_summaries.append(
            {
                "id": composite_id,
                "name": _string(composite.get("name")),
                "fieldCount": len(values),
                "fields": [_schema_item_label(value) for value in values[:10]],
            }
        )

    if not structures and not segments and not composites:
        return _summarize_text(raw_content)
    example_message_type = message_types[0] if message_types else None
    return {
        "version": version,
        "messageType": example_message_type,
        "exampleMessageType": example_message_type,
        "messageTypes": message_types[:24],
        "counts": {
            "structures": len(structures),
            "segments": len(segments),
            "composites": len(composites),
            "fields": field_count,
            "requiredHints": len(required_hints),
            "repeatingHints": len(repeating_hints),
        },
        "structures": structure_summaries[:20],
        "segments": segment_summaries[:40],
        "composites": composite_summaries[:30],
        "requiredHints": required_hints[:40],
        "repeatingHints": repeating_hints[:40],
    }


def _summarize_json_schema(parsed: Any, raw_content: str) -> dict[str, Any]:
    document = parsed if isinstance(parsed, dict) else _try_json(raw_content)
    if not isinstance(document, dict):
        return _summarize_text(raw_content)
    fields: list[dict[str, Any]] = []
    required_hints: list[str] = []

    def walk(schema: dict[str, Any], prefix: str = "") -> None:
        required = set(schema.get("required") or [])
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return
        for name, child in properties.items():
            path = f"{prefix}.{name}" if prefix else str(name)
            child_schema = child if isinstance(child, dict) else {}
            fields.append(
                {
                    "path": path,
                    "type": child_schema.get("type"),
                    "required": name in required,
                }
            )
            if name in required:
                required_hints.append(path)
            if isinstance(child, dict):
                walk(child, path)

    walk(document)
    definitions = document.get("$defs") or document.get("definitions") or {}
    if isinstance(definitions, dict):
        for definition in definitions.values():
            if isinstance(definition, dict):
                walk(definition)
    title = _string(document.get("title"))
    return {
        "messageType": title,
        "exampleMessageType": title,
        "messageTypes": [title] if title else [],
        "counts": {
            "structures": 1 if title else 0,
            "segments": 0,
            "composites": len(definitions) if isinstance(definitions, dict) else 0,
            "fields": len(fields),
            "requiredHints": len(required_hints),
            "repeatingHints": 0,
        },
        "fields": fields[:80],
        "requiredHints": required_hints[:40],
        "repeatingHints": [],
    }


def _summarize_xml_schema(raw_content: str) -> dict[str, Any]:
    element_names = re.findall(
        r"<(?:xs:|xsd:)?element\b[^>]*\bname=['\"]([^'\"]+)['\"]",
        raw_content,
    )
    complex_types = re.findall(
        r"<(?:xs:|xsd:)?complexType\b[^>]*\bname=['\"]([^'\"]+)['\"]",
        raw_content,
    )
    simple_types = re.findall(
        r"<(?:xs:|xsd:)?simpleType\b[^>]*\bname=['\"]([^'\"]+)['\"]",
        raw_content,
    )
    required_hints = [
        name
        for name in element_names
        if re.search(
            rf"\bname=['\"]{re.escape(name)}['\"][^>]*(?:minOccurs=['\"]1['\"]|use=['\"]required['\"])",
            raw_content,
        )
    ]
    repeating_hints = [
        name
        for name in element_names
        if re.search(
            rf"\bname=['\"]{re.escape(name)}['\"][^>]*maxOccurs=['\"](?:unbounded|[2-9]\d*)['\"]",
            raw_content,
        )
    ]
    return {
        "messageType": element_names[0] if element_names else None,
        "exampleMessageType": element_names[0] if element_names else None,
        "messageTypes": element_names[:24],
        "counts": {
            "structures": len(complex_types),
            "segments": len(element_names),
            "composites": len(simple_types),
            "fields": len(element_names),
            "requiredHints": len(required_hints),
            "repeatingHints": len(repeating_hints),
        },
        "structures": [{"id": name, "name": name} for name in complex_types[:30]],
        "segments": [{"id": name, "name": name, "fieldCount": 0} for name in element_names[:40]],
        "requiredHints": required_hints[:40],
        "repeatingHints": repeating_hints[:40],
    }


def _summarize_delimited_or_fixed_width(
    parsed: Any, raw_content: str, schema_format: str
) -> dict[str, Any]:
    document = parsed if isinstance(parsed, dict) else {}
    configured_fields = document.get("fields") or document.get("columns")
    fields: list[dict[str, Any]] = []
    if isinstance(configured_fields, list):
        for index, item in enumerate(configured_fields, start=1):
            if isinstance(item, dict):
                fields.append(
                    {
                        "name": (
                            _string(item.get("name"))
                            or _string(item.get("id"))
                            or f"field{index}"
                        ),
                        "type": _string(item.get("type")),
                        "position": item.get("position") or item.get("start"),
                        "length": item.get("length"),
                        "required": bool(item.get("required") or item.get("usage") == "R"),
                    }
                )
            else:
                fields.append({"name": str(item), "position": index})
    if not fields:
        fields = _infer_delimited_fields(raw_content, schema_format)
    required_hints = [
        str(field.get("name"))
        for field in fields
        if field.get("required") and field.get("name") is not None
    ]
    message_type = _string(document.get("messageType") or document.get("recordType"))
    return {
        "messageType": message_type,
        "exampleMessageType": message_type,
        "messageTypes": [message_type] if message_type else [],
        "counts": {
            "structures": 1 if fields else 0,
            "segments": 0,
            "composites": 0,
            "fields": len(fields),
            "requiredHints": len(required_hints),
            "repeatingHints": 0,
        },
        "fields": fields[:80],
        "requiredHints": required_hints[:40],
        "repeatingHints": [],
    }


def _summarize_text(raw_content: str) -> dict[str, Any]:
    lines = [line for line in raw_content.splitlines() if line.strip()]
    return {
        "messageType": None,
        "exampleMessageType": None,
        "messageTypes": [],
        "counts": {
            "structures": 0,
            "segments": len(lines),
            "composites": 0,
            "fields": 0,
            "requiredHints": 0,
            "repeatingHints": 0,
        },
        "fields": [],
        "requiredHints": [],
        "repeatingHints": [],
    }


def _parse_structured_content(raw_content: str, schema_format: str) -> Any:
    text = raw_content.strip()
    if not text:
        return None
    if schema_format == "xml_schema":
        return None
    if schema_format == "json_schema":
        parsed = _try_json(text)
        if parsed is not None:
            return parsed
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _try_json(raw_content: str) -> Any:
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        return None


def _infer_delimited_fields(raw_content: str, schema_format: str) -> list[dict[str, Any]]:
    lines = [line for line in raw_content.splitlines() if line.strip()]
    if not lines:
        return []
    if schema_format == "fixed_width":
        tokens = [token for token in re.split(r"\s{2,}", lines[0].strip()) if token]
        return [{"name": token, "position": index} for index, token in enumerate(tokens, start=1)]
    sample = "\n".join(lines[:3])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(lines[0]), dialect)
    first_row = next(reader, [])
    return [
        {"name": value.strip() or f"column{index}", "position": index}
        for index, value in enumerate(first_row, start=1)
    ]


def _flatten_schema_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for item in items:
        flattened.append(item)
        group_items = _as_dict_list(item.get("items"))
        if group_items:
            flattened.extend(_flatten_schema_items(group_items))
    return flattened


def _required_hints(items: list[dict[str, Any]], owner: str | None) -> list[str]:
    hints = []
    for item in items:
        usage = _string(item.get("usage")) or ""
        if usage.upper() in {"R", "RE", "M", "MANDATORY", "REQUIRED"}:
            label = _schema_item_label(item)
            if label:
                hints.append(f"{owner}.{label}" if owner else label)
    return hints


def _repeating_hints(items: list[dict[str, Any]], owner: str | None) -> list[str]:
    hints = []
    for item in items:
        count = _string(item.get("count")) or _string(item.get("maxOccurs"))
        if not count or count in {"0", "1"}:
            continue
        label = _schema_item_label(item)
        if label:
            hint = f"{owner}.{label} repeats {count}" if owner else f"{label} repeats {count}"
            hints.append(hint)
    return hints


def _schema_item_label(item: dict[str, Any]) -> str | None:
    return (
        _string(item.get("idRef"))
        or _string(item.get("id"))
        or _string(item.get("groupId"))
        or _string(item.get("name"))
    )


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _limit(value: Any, count: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:count]


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 24].rstrip() + "\n... [truncated]"
