"""Tests for target (egress) and bidirectional MI generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service


@pytest.fixture(autouse=True)
def _runs_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()


def _target_canonical() -> dict:
    """A minimal canonical model for a Target MI (Solace -> REST sink)."""
    return {
        "title": "Order Webhook Sink",
        "serviceName": "order-webhook-sink",
        "serviceVersion": "1.0.0",
        "servers": [],
        "authSchemes": [],
        "operations": [
            {
                "operationId": "forwardOrder",
                "method": "POST",
                "path": "/webhook/orders",
                "summary": "Forward order events",
                "tags": ["orders"],
                "requestSchemaName": None,
                "responseSchemaName": None,
                "requestSchema": None,
                "responseSchema": None,
                "emitsEvent": True,
                "eventCandidates": [
                    {
                        "operationId": "forwardOrder",
                        "canonicalEventName": "OrderCreated",
                        "topicName": "orders/order/created/v1",
                        "schemaName": "OrderCreatedPayload",
                        "applicationName": "order-webhook-sink-integration",
                        "emitsEvent": True,
                    }
                ],
            }
        ],
        "topics": ["orders/order/created/v1"],
        "schemaNames": ["OrderCreatedPayload"],
        "applicationNames": ["order-webhook-sink-integration"],
        "stripeEnabled": False,
        "testFixtures": [],
        "ingressType": "rest_controller",
        "direction": "target",
        "targetPattern": "rest_sink",
    }


def test_target_mi_generates_solace_consumer() -> None:
    """Target MI generates SolaceConsumerService (subscribes from Solace)."""
    canonical = _target_canonical()
    ws = generator_service.generate("target-test", canonical, {}, "")

    assert (ws / "pom.xml").exists()
    assert (
        ws / "src/main/java/com/spec2event/generated/service/SolaceConsumerService.java"
    ).exists()
    assert (
        ws / "src/main/java/com/spec2event/generated/service/TargetDispatcherService.java"
    ).exists()


def test_target_mi_generates_rest_sink() -> None:
    """Target MI with rest_sink pattern generates RestTargetSinkService."""
    canonical = _target_canonical()
    ws = generator_service.generate("target-rest-test", canonical, {}, "")

    assert (
        ws / "src/main/java/com/spec2event/generated/service/RestTargetSinkService.java"
    ).exists()


def test_target_mi_generates_binding_factories() -> None:
    """Target MI generates target-side binding capabilities factories."""
    canonical = _target_canonical()
    ws = generator_service.generate("target-binding-test", canonical, {}, "")

    assert (
        ws
        / "src/main/java/com/spec2event/generated/binding"
        / "TargetConsumerBindingCapabilitiesFactory.java"
    ).exists()
    assert (
        ws
        / "src/main/java/com/spec2event/generated/binding"
        / "TargetProducerBindingCapabilitiesFactory.java"
    ).exists()


def test_target_mi_does_not_generate_source_controller() -> None:
    """Target MI should NOT generate GeneratedApiController."""
    canonical = _target_canonical()
    ws = generator_service.generate("target-no-source-test", canonical, {}, "")

    assert not (
        ws / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java"
    ).exists()


def test_bidirectional_mi_generates_both_sides() -> None:
    """Bidirectional MI generates both source controller and target consumer."""
    canonical = _target_canonical()
    canonical["direction"] = "bidirectional"
    canonical["serviceName"] = "order-bidi"

    ws = generator_service.generate("bidi-test", canonical, {}, "")

    # Source side
    assert (
        ws / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java"
    ).exists()
    # Target side
    assert (
        ws / "src/main/java/com/spec2event/generated/service/SolaceConsumerService.java"
    ).exists()
    assert (
        ws / "src/main/java/com/spec2event/generated/service/RestTargetSinkService.java"
    ).exists()


def test_source_mi_unchanged_by_target_support() -> None:
    """Source MIs with no targetPattern remain unchanged."""
    canonical = _target_canonical()
    canonical["direction"] = "source"
    canonical.pop("targetPattern")

    ws = generator_service.generate("source-only-test", canonical, {}, "")

    # Source side generated
    assert (
        ws / "src/main/java/com/spec2event/generated/api/GeneratedApiController.java"
    ).exists()
    # Target side NOT generated
    assert not (
        ws / "src/main/java/com/spec2event/generated/service/SolaceConsumerService.java"
    ).exists()
