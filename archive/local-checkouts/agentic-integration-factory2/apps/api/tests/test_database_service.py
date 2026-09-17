from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from spec2event.config import get_settings
from spec2event.services.database_generator_service import database_generator_service
from spec2event.services.database_service import canonicalize_database


def _discovery_summary() -> dict:
    return {
        "databaseKind": "postgres",
        "databaseName": "defaultdb",
        "schema": "public",
        "visibleTables": ["public.products"],
        "selectedTable": "products",
        "selectedTableQualifiedName": "public.products",
        "databaseVersion": "PostgreSQL 16",
        "rowCount": 1_000_000,
        "columns": [
            {"name": "id", "dataType": "integer", "nullable": False},
            {"name": "sku", "dataType": "character varying", "nullable": False},
            {"name": "name", "dataType": "character varying", "nullable": False},
            {"name": "category", "dataType": "character varying", "nullable": True},
            {"name": "price", "dataType": "numeric", "nullable": False},
            {"name": "stock_quantity", "dataType": "integer", "nullable": False},
            {"name": "created_at", "dataType": "timestamp without time zone", "nullable": False},
            {"name": "updated_at", "dataType": "timestamp without time zone", "nullable": False},
        ],
        "primaryKeyColumns": ["id"],
        "idColumn": "id",
        "createdColumn": "created_at",
        "updatedColumn": "updated_at",
        "sampleRows": [
            {
                "id": 1,
                "sku": "SKU-1",
                "name": "Electronics-1",
                "category": "Electronics",
                "price": 492.89,
                "stock_quantity": 47,
                "created_at": "2026-02-20T12:43:56.481631",
                "updated_at": "2026-02-20T12:43:56.481631",
            }
        ],
        "adapterPattern": "initial_snapshot_plus_incremental_polling",
        "recommendedStrategy": "Use initial snapshot plus incremental polling on updated_at.",
        "riskNotes": [],
    }


def test_canonicalize_database_derives_expected_runtime_shape() -> None:
    canonical_model = canonicalize_database(
        _discovery_summary(),
        application_domain_name="Commerce Source Integrations",
        topic_root="commerce",
    )

    assert canonical_model["sourceMode"] == "database"
    assert canonical_model["serviceName"] == "postgres-products"
    assert canonical_model["applicationDomainName"] == "Commerce Source Integrations"
    assert len(canonical_model["topics"]) >= 12
    assert "commerce/postgres-products/product/observed/v1" in canonical_model["topics"]
    assert "commerce/postgres-products/product/updated/v1" in canonical_model["topics"]
    assert "commerce/postgres-products/product/price/changed/v1" in canonical_model["topics"]
    assert "commerce/postgres-products/product/inventory/restocked/v1" in canonical_model["topics"]
    assert canonical_model["applicationNames"] == ["postgres-products-integration"]
    assert canonical_model["operations"][0]["eventCandidates"]
    assert any(
        candidate["schemaName"] == "ProductPriceChangedPayload"
        for candidate in canonical_model["operations"][0]["eventCandidates"]
    )
    assert canonical_model["headerContract"]["schemaFormat"] == "json-schema"
    assert canonical_model["databaseConfig"]["watermarkColumn"] == "updated_at"
    assert canonical_model["databaseConfig"]["businessColumns"] == [
        "sku",
        "name",
        "category",
        "price",
        "stock_quantity",
    ]


def test_database_generator_writes_workspace(monkeypatch, tmp_path: Path) -> None:
    discovery = _discovery_summary()
    canonical_model = canonicalize_database(discovery, topic_root="commerce")
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    workspace = database_generator_service.generate("pytest-db-run", canonical_model, discovery)

    assert (workspace / "pom.xml").exists()
    assert (workspace / "README.md").exists()
    assert (
        workspace
        / "src/main/java/com/spec2event/generated/api/DatabasePollingController.java"
    ).exists()
    assert (
        workspace
        / "src/main/java/com/spec2event/generated/service/DatabasePollingService.java"
    ).exists()
    assert (workspace / "source-discovery.json").exists()
    application_yml = (workspace / "src/main/resources/application.yml").read_text(encoding="utf-8")
    assert "productPriceChanged" in application_yml
    assert "productRestocked" in application_yml
    canonical_event_service = (
        workspace
        / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java"
    ).read_text(encoding="utf-8")
    assert "ProductPriceChanged" in canonical_event_service
    assert "ProductRestocked" in canonical_event_service
    assert "schemaSubject" in canonical_event_service


@pytest.mark.integration
def test_generated_database_project_compiles_with_maven(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if shutil.which("mvn") is None:
        pytest.skip("mvn is not installed")

    discovery = _discovery_summary()
    canonical_model = canonicalize_database(discovery, topic_root="commerce")
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    workspace = database_generator_service.generate("pytest-db-maven-run", canonical_model, discovery)

    subprocess.run(
        ["mvn", "-q", "test"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["mvn", "-q", "-DskipTests", "package"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
