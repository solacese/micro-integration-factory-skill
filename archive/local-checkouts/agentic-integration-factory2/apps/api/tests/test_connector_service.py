from __future__ import annotations

from pathlib import Path

from spec2event.config import get_settings
from spec2event.services.connector_generator_service import connector_generator_service
from spec2event.services.connector_spec_service import (
    canonicalize_connector_spec,
    summarize_connector_spec,
)


def _file_spec() -> dict:
    return {
        "sourceMode": "file",
        "name": "Nightly Inventory Drops",
        "version": "1.0.0",
        "applicationDomainName": "Supply Chain Source Integrations",
        "topicRoot": "supply",
        "sourceDetails": {
            "inputDirectory": "./demo/inventory/inbox",
            "archiveDirectory": "./demo/inventory/archive",
            "pollIntervalSeconds": 30,
        },
        "events": [
            {
                "name": "InventorySnapshotObserved",
                "entity": "inventory",
                "action": "observed",
            }
        ],
    }


def _kafka_spec() -> dict:
    return {
        "sourceMode": "kafka",
        "name": "Orders Topic Bridge",
        "version": "1.0.0",
        "applicationDomainName": "Commerce Source Integrations",
        "topicRoot": "commerce",
        "sourceDetails": {
            "stream": "orders.events",
            "consumerGroup": "solace-orders-bridge",
        },
        "events": [
            {
                "name": "OrderCreated",
                "entity": "order",
                "action": "created",
            }
        ],
    }


def test_canonicalize_connector_spec_derives_runtime_shape() -> None:
    canonical_model = canonicalize_connector_spec(_kafka_spec())

    assert canonical_model["sourceMode"] == "kafka"
    assert canonical_model["adapterType"] == "kafka-consumer-bridge"
    assert canonical_model["runtimeBlueprint"] == "bridge_starter"
    assert canonical_model["topics"] == ["commerce/orders-topic-bridge/order/created/v1"]
    assert canonical_model["testFixtures"][0]["path"] == "/internal/source/emit"


def test_connector_generator_writes_file_poller_workspace(
    monkeypatch,
    tmp_path: Path,
) -> None:
    spec = _file_spec()
    summary = summarize_connector_spec(spec)
    canonical_model = canonicalize_connector_spec(spec)
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    workspace = connector_generator_service.generate(
        "pytest-connector-run",
        canonical_model,
        summary,
    )

    assert (workspace / "pom.xml").exists()
    assert (workspace / "README.md").exists()
    assert (
        workspace / "src/main/java/com/spec2event/generated/api/SourceTriggerController.java"
    ).exists()
    assert (
        workspace / "src/main/java/com/spec2event/generated/service/SourcePollingService.java"
    ).exists()
    assert (workspace / "source-summary.json").exists()
