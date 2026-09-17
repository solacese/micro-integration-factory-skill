from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import psycopg

DEFAULT_CONTENT_TYPE = "application/json"
DEFAULT_SCHEMA_FORMAT = "json-schema"
DEFAULT_SERDE_FAMILY = "jackson-json"
DEFAULT_COMPATIBILITY_MODE = "backward_additive"
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_SCHEMA_VERSIONING_POLICY = "topic-major-schema-additive"
DEFAULT_REGISTRY_COORDINATES = "event-portal-only"
DEFAULT_REQUIRED_HEADERS = [
    "content-type",
    "event-type",
    "schema-name",
    "schema-version",
    "source-system",
    "source-record-id",
    "correlation-id",
    "occurred-at",
]


def discover_database_source(
    *,
    database_url: str | None = None,
    host: str | None = None,
    port: int | None = None,
    database_name: str | None = None,
    username: str | None = None,
    password: str | None = None,
    schema: str = "public",
    preferred_table: str = "products",
    sslmode: str = "require",
) -> dict[str, Any]:
    connection_url = database_url or _build_connection_url(
        host=host,
        port=port or 5432,
        database_name=database_name,
        username=username,
        password=password,
        sslmode=sslmode,
    )
    if not connection_url:
        raise ValueError("Database connection details are missing")

    with psycopg.connect(connection_url) as conn:
        with conn.cursor() as cur:
            cur.execute("select version()")
            version = cur.fetchone()[0]

            cur.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = %s and table_type = 'BASE TABLE'
                order by table_name
                """,
                (schema,),
            )
            table_names = [row[0] for row in cur.fetchall()]
            if not table_names:
                raise ValueError(f"No tables found in schema {schema}")

            selected_table = (
                preferred_table if preferred_table in table_names else _pick_table(table_names)
            )
            columns = _columns(cur, schema, selected_table)
            primary_key_columns = _primary_key_columns(cur, schema, selected_table)
            row_count = _row_count(cur, schema, selected_table)
            sample_rows = _sample_rows(cur, schema, selected_table, columns)

    updated_column = _first_matching(
        (column["name"] for column in columns),
        ["updated_at", "updated_on", "modified_at", "modified_on"],
    )
    created_column = _first_matching(
        (column["name"] for column in columns),
        ["created_at", "created_on", "inserted_at"],
    )
    id_column = primary_key_columns[0] if primary_key_columns else _first_matching(
        (column["name"] for column in columns),
        ["id"],
    )

    risks: list[str] = []
    if not updated_column:
        risks.append(
            "No obvious updated timestamp column was found; "
            "incremental polling would be weaker."
        )
    if not id_column:
        risks.append(
            "No obvious primary key column was found; "
            "ordering and idempotency would need extra care."
        )

    return {
        "databaseKind": "postgres",
        "databaseName": database_name or _database_name_from_url(connection_url),
        "schema": schema,
        "visibleTables": [f"{schema}.{name}" for name in table_names],
        "selectedTable": selected_table,
        "selectedTableQualifiedName": f"{schema}.{selected_table}",
        "databaseVersion": version,
        "rowCount": row_count,
        "columns": columns,
        "primaryKeyColumns": primary_key_columns,
        "idColumn": id_column,
        "createdColumn": created_column,
        "updatedColumn": updated_column,
        "sampleRows": sample_rows,
        "adapterPattern": "initial_snapshot_plus_incremental_polling",
        "recommendedStrategy": (
            "Use initial snapshot plus incremental polling on "
            f"{updated_column or 'the selected watermark column'}."
        ),
        "riskNotes": risks,
    }


def canonicalize_database(
    discovery: dict[str, Any],
    *,
    application_domain_name: str | None = None,
    topic_root: str = "commerce",
) -> dict[str, Any]:
    table_name = discovery["selectedTable"]
    entity_name = _singularize(table_name)
    entity_title = _pascal(entity_name)
    service_name = _safe_slug(f"{discovery['databaseKind']}-{table_name}")
    title = f"PostgreSQL {entity_title} Source"
    application_name = f"{service_name}-integration"
    record_schema_name = f"{entity_title}Record"
    operation_id = f"poll{entity_title}s"
    record_schema = _record_schema(discovery["columns"], discovery.get("sampleRows") or [])
    event_candidates = _database_event_candidates(
        discovery=discovery,
        topic_root=topic_root,
        service_name=service_name,
        entity_name=entity_name,
        entity_title=entity_title,
        application_name=application_name,
    )
    topic_names = sorted({candidate["topicName"] for candidate in event_candidates})
    event_schema_names = {candidate["schemaName"] for candidate in event_candidates}

    return {
        "title": title,
        "applicationDomainName": application_domain_name,
        "serviceName": service_name,
        "serviceVersion": "1.0.0",
        "sourceMode": "database",
        "adapterType": "database-polling",
        "runtimeBlueprint": "database_poller",
        "operations": [
            {
                "operationId": operation_id,
                "method": "POLL",
                "path": discovery["selectedTableQualifiedName"],
                "summary": (
                    f"Initial snapshot plus incremental polling on "
                    f"{discovery['selectedTableQualifiedName']}"
                ),
                "tags": ["database", table_name],
                "requestSchemaName": record_schema_name,
                "responseSchemaName": None,
                "requestSchema": record_schema,
                "responseSchema": None,
                "emitsEvent": True,
                "eventCandidates": event_candidates,
            }
        ],
        "topics": topic_names,
        "schemaNames": sorted({*event_schema_names, record_schema_name}),
        "applicationNames": [application_name],
        "stripeEnabled": False,
        "headerContract": _header_contract(),
        "compatibilityPolicy": DEFAULT_COMPATIBILITY_MODE,
        "testFixtures": [
            {
                "operationId": operation_id,
                "label": f"POST /internal/database/poll-now ({table_name})",
                "method": "POST",
                "path": "/internal/database/poll-now",
                "payload": {"limit": 5},
            }
        ],
        "databaseDiscovery": discovery,
        "databaseConfig": {
            "schema": discovery["schema"],
            "table": table_name,
            "idColumn": discovery.get("idColumn") or "id",
            "watermarkColumn": (
                discovery.get("updatedColumn") or discovery.get("createdColumn") or "id"
            ),
            "createdColumn": discovery.get("createdColumn"),
            "updatedColumn": discovery.get("updatedColumn"),
            "businessColumns": _business_columns(discovery["columns"], discovery).copy(),
        },
    }


def _build_connection_url(
    *,
    host: str | None,
    port: int,
    database_name: str | None,
    username: str | None,
    password: str | None,
    sslmode: str,
) -> str | None:
    if not host or not database_name or not username or password is None:
        return None
    return (
        f"postgresql://{quote(username)}:{quote(password)}@{host}:{port}/{database_name}"
        f"?sslmode={quote(sslmode)}"
    )


def _database_name_from_url(connection_url: str) -> str:
    path = connection_url.rsplit("/", 1)[-1]
    return path.split("?", 1)[0]


def _pick_table(table_names: list[str]) -> str:
    preferred_order = ["products", "orders", "customers", "users"]
    for name in preferred_order:
        if name in table_names:
            return name
    for name in table_names:
        if not name.startswith(("alembic_", "app_", "user_", "session_", "event_")):
            return name
    return table_names[0]


def _header_contract() -> dict[str, Any]:
    return {
        "contentType": DEFAULT_CONTENT_TYPE,
        "requiredHeaders": list(DEFAULT_REQUIRED_HEADERS),
        "schemaFormat": DEFAULT_SCHEMA_FORMAT,
        "serializerFamily": DEFAULT_SERDE_FAMILY,
        "deserializerFamily": DEFAULT_SERDE_FAMILY,
        "schemaVersion": DEFAULT_SCHEMA_VERSION,
        "compatibilityMode": DEFAULT_COMPATIBILITY_MODE,
        "schemaVersioningPolicy": DEFAULT_SCHEMA_VERSIONING_POLICY,
        "registryCoordinates": DEFAULT_REGISTRY_COORDINATES,
    }


def _event_contract(
    *,
    schema_name: str,
    application_name: str,
    source_system: str,
    summary: str,
    payload_example: dict[str, Any],
    match_strategy: dict[str, Any],
) -> dict[str, Any]:
    header_contract = _header_contract()
    return {
        "schemaFormat": header_contract["schemaFormat"],
        "contentType": header_contract["contentType"],
        "serializerFamily": header_contract["serializerFamily"],
        "deserializerFamily": header_contract["deserializerFamily"],
        "schemaSubject": f"{application_name}.{schema_name}",
        "schemaVersion": header_contract["schemaVersion"],
        "schemaVersioningPolicy": header_contract["schemaVersioningPolicy"],
        "registryCoordinates": header_contract["registryCoordinates"],
        "compatibilityMode": header_contract["compatibilityMode"],
        "requiredHeaders": list(header_contract["requiredHeaders"]),
        "sourceSystem": source_system,
        "payloadExample": payload_example,
        "summary": summary,
        "matchStrategy": match_strategy,
    }


def _database_event_candidates(
    *,
    discovery: dict[str, Any],
    topic_root: str,
    service_name: str,
    entity_name: str,
    entity_title: str,
    application_name: str,
) -> list[dict[str, Any]]:
    sample_row = (discovery.get("sampleRows") or [{}])[0] or {}
    source_system = discovery.get("databaseKind") or "postgres"
    event_candidates: list[dict[str, Any]] = []
    operation_id = f"poll{entity_title}s"

    def add_event(
        *,
        event_name: str,
        topic_suffix: str,
        summary: str,
        match_strategy: dict[str, Any],
    ) -> None:
        schema_name = f"{event_name}Payload"
        event_candidates.append(
            {
                "operationId": operation_id,
                "canonicalEventName": event_name,
                "topicName": f"{topic_root}/{service_name}/{topic_suffix}/v1",
                "schemaName": schema_name,
                "applicationName": application_name,
                "emitsEvent": True,
                **_event_contract(
                    schema_name=schema_name,
                    application_name=application_name,
                    source_system=source_system,
                    summary=summary,
                    payload_example=sample_row,
                    match_strategy=match_strategy,
                ),
            }
        )

    add_event(
        event_name=f"{entity_title}Observed",
        topic_suffix=f"{entity_name}/observed",
        summary=f"{entity_title} row observed during polling.",
        match_strategy={"kind": "always"},
    )
    add_event(
        event_name=f"{entity_title}Created",
        topic_suffix=f"{entity_name}/created",
        summary=f"{entity_title} row first seen or created.",
        match_strategy={"kind": "created"},
    )
    add_event(
        event_name=f"{entity_title}Updated",
        topic_suffix=f"{entity_name}/updated",
        summary=f"{entity_title} row changed since the previous poll.",
        match_strategy={"kind": "row_changed"},
    )
    add_event(
        event_name=f"{entity_title}Changed",
        topic_suffix=f"{entity_name}/changed",
        summary=f"{entity_title} row produced one or more tracked field changes.",
        match_strategy={"kind": "any_business_field_changed"},
    )

    for column_name in _business_columns(discovery["columns"], discovery):
        column_slug = _safe_slug(column_name).replace("-", "_")
        add_event(
            event_name=f"{entity_title}{_pascal(column_name)}Changed",
            topic_suffix=f"{entity_name}/{column_slug}/changed",
            summary=f"{entity_title} {column_name} changed.",
            match_strategy={"kind": "column_changed", "column": column_name},
        )

    if any(column["name"] == "stock_quantity" for column in discovery["columns"]):
        add_event(
            event_name=f"{entity_title}InventoryIncreased",
            topic_suffix=f"{entity_name}/inventory/increased",
            summary=f"{entity_title} inventory increased.",
            match_strategy={"kind": "numeric_increase", "column": "stock_quantity"},
        )
        add_event(
            event_name=f"{entity_title}InventoryDecreased",
            topic_suffix=f"{entity_name}/inventory/decreased",
            summary=f"{entity_title} inventory decreased.",
            match_strategy={"kind": "numeric_decrease", "column": "stock_quantity"},
        )
        add_event(
            event_name=f"{entity_title}InventoryDepleted",
            topic_suffix=f"{entity_name}/inventory/depleted",
            summary=f"{entity_title} inventory crossed to zero or below.",
            match_strategy={
                "kind": "crosses_threshold",
                "column": "stock_quantity",
                "fromGreaterThan": 0,
                "toLessOrEqual": 0,
            },
        )
        add_event(
            event_name=f"{entity_title}Restocked",
            topic_suffix=f"{entity_name}/inventory/restocked",
            summary=f"{entity_title} inventory crossed from zero or below to above zero.",
            match_strategy={
                "kind": "crosses_threshold",
                "column": "stock_quantity",
                "fromLessOrEqual": 0,
                "toGreaterThan": 0,
            },
        )

    return event_candidates


def _business_columns(
    columns: list[dict[str, Any]], discovery: dict[str, Any]
) -> list[str]:
    reserved = {
        *(discovery.get("primaryKeyColumns") or []),
        discovery.get("idColumn"),
        discovery.get("createdColumn"),
        discovery.get("updatedColumn"),
    }
    return [
        column["name"]
        for column in columns
        if column["name"] not in reserved
    ]


def _columns(cur: psycopg.Cursor[Any], schema: str, table_name: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        select column_name, data_type, is_nullable
        from information_schema.columns
        where table_schema = %s and table_name = %s
        order by ordinal_position
        """,
        (schema, table_name),
    )
    return [
        {
            "name": row[0],
            "dataType": row[1],
            "nullable": row[2] == "YES",
        }
        for row in cur.fetchall()
    ]


def _primary_key_columns(
    cur: psycopg.Cursor[Any], schema: str, table_name: str
) -> list[str]:
    cur.execute(
        """
        select kcu.column_name
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
          on tc.constraint_name = kcu.constraint_name
         and tc.table_schema = kcu.table_schema
         and tc.table_name = kcu.table_name
        where tc.constraint_type = 'PRIMARY KEY'
          and tc.table_schema = %s
          and tc.table_name = %s
        order by kcu.ordinal_position
        """,
        (schema, table_name),
    )
    return [row[0] for row in cur.fetchall()]


def _row_count(cur: psycopg.Cursor[Any], schema: str, table_name: str) -> int:
    cur.execute(f'select count(*) from "{schema}"."{table_name}"')
    return int(cur.fetchone()[0])


def _sample_rows(
    cur: psycopg.Cursor[Any],
    schema: str,
    table_name: str,
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    column_names = [column["name"] for column in columns[:10]]
    rendered_columns = ", ".join(f'"{name}"' for name in column_names)
    order_column = (
        _first_matching(column_names, ["updated_at", "created_at", "id"]) or column_names[0]
    )
    cur.execute(
        f'''
        select {rendered_columns}
        from "{schema}"."{table_name}"
        order by "{order_column}" desc nulls last
        limit 3
        '''
    )
    rows = []
    for raw_row in cur.fetchall():
        rows.append(
            {
                column_name: _json_safe(value)
                for column_name, value in zip(column_names, raw_row, strict=True)
            }
        )
    return rows


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _record_schema(
    columns: list[dict[str, Any]], sample_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    examples = sample_rows[0] if sample_rows else {}
    properties = {
        column["name"]: _column_schema(column["dataType"], examples.get(column["name"]))
        for column in columns
    }
    required = [column["name"] for column in columns if not column["nullable"]]
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _column_schema(data_type: str, example: Any) -> dict[str, Any]:
    lowered = data_type.lower()
    if lowered in {"integer", "bigint", "smallint"}:
        schema: dict[str, Any] = {"type": "integer"}
    elif lowered in {"numeric", "decimal", "real", "double precision"}:
        schema = {"type": "number"}
    elif lowered == "boolean":
        schema = {"type": "boolean"}
    elif lowered in {"date"}:
        schema = {"type": "string", "format": "date"}
    elif "time" in lowered:
        schema = {"type": "string", "format": "date-time"}
    elif lowered in {"json", "jsonb"}:
        schema = {"type": "object", "additionalProperties": True}
    else:
        schema = {"type": "string"}
    if example is not None:
        schema["example"] = example
    return schema


def _first_matching(values: Iterable[str], preferred: list[str]) -> str | None:
    lowered_map = {value.lower(): value for value in values}
    for name in preferred:
        if name in lowered_map:
            return lowered_map[name]
    return None


def _safe_slug(text: str) -> str:
    lowered = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    parts = [part for part in lowered.split("-") if part]
    return "-".join(parts) or "generated-service"


def _pascal(text: str) -> str:
    parts = [
        part for part in "".join(ch if ch.isalnum() else " " for ch in text).split() if part
    ]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _singularize(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("s") and not value.endswith("ss"):
        return value[:-1]
    return value
