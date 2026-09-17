from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from spec2event.adapters.portal.solace_event_portal import SolaceEventPortalAdapter
from spec2event.config import get_settings
from spec2event.one_shot_hybrid import _validate_consumer_observation
from spec2event.services.generator_service import generator_service
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
STRIPE_SPEC = REPO_ROOT / "samples" / "openapi" / "stripe-webhook-demo.yaml"


def _stripe_model() -> tuple[dict, dict, str]:
    raw_spec = STRIPE_SPEC.read_text(encoding="utf-8")
    document = load_openapi_document(raw_spec)
    return canonicalize_openapi(document), summarize_openapi(document), raw_spec


def test_event_portal_adapter_returns_manual_actions_when_unconfigured() -> None:
    canonical_model, _, _ = _stripe_model()

    result = SolaceEventPortalAdapter(base_url=None, token=None).sync(canonical_model)

    assert result.status == "not_configured"
    assert result.items
    assert all(item.manual_action for item in result.items)
    assert any(
        item.request_payload
        and item.request_payload["name"] == "StripePaymentIntentSucceeded"
        and item.request_payload["serializerFamily"] == "jackson-json"
        and item.request_payload["contentType"] == "application/json"
        for item in result.items
    )


def test_event_portal_adapter_uses_application_domains_and_event_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_model, _, _ = _stripe_model()
    calls: list[tuple[str, str, dict | None, dict | None]] = []
    state: dict[str, list[dict]] = {
        "applicationDomains": [],
        "applications": [],
        "applicationVersions": [],
        "schemas": [],
        "schemaVersions": [],
        "events": [],
        "eventVersions": [],
    }

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float,
    ) -> httpx.Response:
        del headers, timeout
        endpoint = url.removeprefix("https://api.solace.cloud")
        calls.append((method, endpoint, json, params))

        if method == "GET":
            collection = endpoint.split("/")[-1]
            return httpx.Response(200, json={"data": state[collection]})

        if method == "POST":
            collection = endpoint.split("/")[-1]
            record = {"id": f"id-{len(calls)}", **(json or {})}
            state[collection].append(record)
            return httpx.Response(201, json={"data": record})

        if method == "PATCH" and "/applicationVersions/" in endpoint:
            state["applicationVersions"][0] = {
                **state["applicationVersions"][0],
                **(json or {}),
            }
            return httpx.Response(200, json={"data": state["applicationVersions"][0]})

        raise AssertionError(f"Unexpected request: {method} {endpoint}")

    monkeypatch.setattr(httpx, "request", fake_request)

    result = SolaceEventPortalAdapter(
        base_url="https://solace-sso.solace.cloud/ep/designer",
        token="test-token",
    ).sync(canonical_model)

    assert result.status == "completed"
    assert calls[0][0] == "GET"
    assert calls[0][1] == "/api/v2/architecture/applicationDomains"
    assert any(
        method == "POST" and endpoint.endswith("/applicationDomains")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/applications")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/applicationVersions")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/schemas")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/schemaVersions")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/events")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "POST" and endpoint.endswith("/eventVersions")
        for method, endpoint, _, _ in calls
    )
    assert any(
        method == "PATCH" and "/applicationVersions/" in endpoint
        for method, endpoint, _, _ in calls
    )
    schema_payloads = [
        payload
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/schemas")
    ]
    assert schema_payloads
    assert all(payload["schemaType"] == "jsonSchema" for payload in schema_payloads)
    assert all("SerDes:" in payload["description"] for payload in schema_payloads)
    schema_version_payloads = [
        payload
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/schemaVersions")
    ]
    assert schema_version_payloads
    assert all(isinstance(payload["content"], str) for payload in schema_version_payloads)
    assert all("SerDes:" in payload["description"] for payload in schema_version_payloads)
    event_names = [
        payload["name"]
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/events")
    ]
    assert "StripePaymentIntentSucceeded" in event_names
    assert len(event_names) >= 15
    event_version_payloads = [
        payload
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/eventVersions")
    ]
    assert event_version_payloads
    assert event_version_payloads[0]["deliveryDescriptor"]["brokerType"] == "solace"
    assert all("Required headers:" in payload["description"] for payload in event_version_payloads)
    flow_patch = next(
        payload
        for method, endpoint, payload, _ in calls
        if method == "PATCH" and "/applicationVersions/" in endpoint
    )
    assert flow_patch["declaredProducedEventVersionIds"]


def test_event_portal_adapter_emits_serde_envelope_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_model, _, _ = _stripe_model()
    schema_version_payloads: list[dict] = []

    state: dict[str, list[dict]] = {
        "applicationDomains": [],
        "applications": [],
        "applicationVersions": [],
        "schemas": [],
        "schemaVersions": [],
        "events": [],
        "eventVersions": [],
    }

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float,
    ) -> httpx.Response:
        del headers, timeout
        endpoint = url.removeprefix("https://api.solace.cloud")

        if method == "GET":
            collection = endpoint.split("/")[-1]
            return httpx.Response(200, json={"data": state[collection]})

        if method == "POST":
            collection = endpoint.split("/")[-1]
            record = {"id": f"id-{len(state[collection]) + 1}", **(json or {})}
            state[collection].append(record)
            if collection == "schemaVersions" and json is not None:
                schema_version_payloads.append(json)
            return httpx.Response(201, json={"data": record})

        if method == "PATCH" and "/applicationVersions/" in endpoint:
            return httpx.Response(200, json={"data": json or {}})

        raise AssertionError(f"Unexpected request: {method} {endpoint}")

    monkeypatch.setattr(httpx, "request", fake_request)

    result = SolaceEventPortalAdapter(
        base_url="https://solace-sso.solace.cloud/ep/designer",
        token="test-token",
    ).sync(canonical_model)

    assert result.status == "completed"
    assert schema_version_payloads
    first_schema = json.loads(schema_version_payloads[0]["content"])
    assert first_schema["required"] == ["meta", "payload"]
    assert (
        first_schema["properties"]["meta"]["properties"]["contentType"]["const"]
        == "application/json"
    )
    assert (
        first_schema["properties"]["meta"]["properties"]["serializerFamily"]["const"]
        == "jackson-json"
    )
    assert (
        first_schema["properties"]["meta"]["properties"]["deserializerFamily"]["const"]
        == "jackson-json"
    )
    assert "payload" in first_schema["properties"]


def test_event_portal_adapter_prunes_stale_application_version_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical_model, _, _ = _stripe_model()
    canonical_model["applicationDomainName"] = "Commerce Source Integrations"
    application_name = canonical_model["applicationNames"][0]
    patch_payloads: list[dict] = []

    state: dict[str, list[dict]] = {
        "applicationDomains": [
            {"id": "domain-1", "name": canonical_model["applicationDomainName"]}
        ],
        "applications": [
            {
                "id": "app-1",
                "name": application_name,
                "applicationDomainId": "domain-1",
            }
        ],
        "applicationVersions": [
            {
                "id": "version-1",
                "applicationId": "app-1",
                "version": "1.0.0",
                "displayName": "1.0.0",
                "declaredProducedEventVersionIds": ["stale-produced"],
                "declaredConsumedEventVersionIds": ["stale-consumed"],
                "stateId": "1",
            }
        ],
        "schemas": [],
        "schemaVersions": [],
        "events": [],
        "eventVersions": [],
    }

    def fake_request(
        method: str,
        url: str,
        *,
        headers: dict,
        json: dict | None = None,
        params: dict | None = None,
        timeout: float,
    ) -> httpx.Response:
        del headers, timeout, params
        endpoint = url.removeprefix("https://api.solace.cloud")

        if method == "GET":
            collection = endpoint.split("/")[-1]
            return httpx.Response(200, json={"data": state[collection]})

        if method == "POST":
            collection = endpoint.split("/")[-1]
            record = {"id": f"id-{collection}-{len(state[collection]) + 1}", **(json or {})}
            state[collection].append(record)
            return httpx.Response(201, json={"data": record})

        if method == "PATCH" and "/applicationVersions/" in endpoint:
            patch_payloads.append(json or {})
            state["applicationVersions"][0] = {
                **state["applicationVersions"][0],
                **(json or {}),
            }
            return httpx.Response(200, json={"data": state["applicationVersions"][0]})

        raise AssertionError(f"Unexpected request: {method} {endpoint}")

    monkeypatch.setattr(httpx, "request", fake_request)

    result = SolaceEventPortalAdapter(
        base_url="https://solace-sso.solace.cloud/ep/designer",
        token="test-token",
    ).sync(canonical_model)

    assert result.status == "completed"
    assert len(patch_payloads) == 1
    assert patch_payloads[0]["declaredProducedEventVersionIds"] == sorted(
        record["id"] for record in state["eventVersions"]
    )
    assert patch_payloads[0]["declaredConsumedEventVersionIds"] == []


def test_consumer_validation_accepts_matching_serde_contract() -> None:
    canonical_model, _, _ = _stripe_model()
    invocation = {
        "status": 200,
        "payload": {
            "correlationId": "corr-123",
            "publishedTopics": ["payments/stripe/payment_intent/succeeded/v1"],
        },
    }
    message = {
        "topicName": "payments/stripe/payment_intent/succeeded/v1",
        "payload": {
                "meta": {
                    "eventType": "StripePaymentIntentSucceeded",
                    "schemaName": "StripePaymentIntentSucceededPayload",
                    "schemaVersion": "1.0.0",
                    "schemaSubject": (
                        "stripe-payments-gateway-integration."
                        "StripePaymentIntentSucceededPayload"
                    ),
                    "contentType": "application/json",
                    "schemaFormat": "json-schema",
                "serializerFamily": "jackson-json",
                "deserializerFamily": "jackson-json",
                "compatibilityMode": "backward_additive",
                "applicationName": "stripe-payments-gateway-integration",
                "sourceSystem": "stripe",
                "sourceOperationId": "stripe-webhook-payment",
                "sourceRecordId": "pi_demo_123",
                "correlationId": "corr-123",
                "occurredAt": "2026-03-23T12:00:00Z",
            },
            "payload": {
                "id": "evt_demo_123",
                "type": "payment_intent.succeeded",
            },
        },
    }

    validation = _validate_consumer_observation(canonical_model, invocation, message)

    assert validation["status"] == "completed"
    assert validation["topicMatched"] is True
    assert validation["schemaMatched"] is True
    assert validation["correlationMatched"] is True
    assert validation["missingMetadata"] == []


def test_generator_writes_mdk_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canonical_model, summary, raw_spec = _stripe_model()
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    workspace = generator_service.generate("pytest-run", canonical_model, summary, raw_spec)

    assert (workspace / "pom.xml").exists()
    assert (workspace / "Dockerfile").exists()
    assert (workspace / "helm" / "Chart.yaml").exists()
    assert (
        workspace
        / "src/main/java/com/spec2event/generated/api/StripeWebhookController.java"
    ).exists()
    assert (workspace / "ui/ui-metadata.json").exists()
    publisher_service = (
        workspace
        / "src/main/java/com/spec2event/generated/service/SolacePublisherService.java"
    ).read_text(encoding="utf-8")
    assert 'setHeader("schema-name"' in publisher_service
    assert 'setHeader("schema-version"' in publisher_service
    assert 'metadata.put("serializerFamily"' in publisher_service
    canonical_event_service = (
        workspace
        / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java"
    ).read_text(encoding="utf-8")
    assert "payment_intent.succeeded" in canonical_event_service
    assert "checkout.session.completed" in canonical_event_service


@pytest.mark.integration
def test_generated_project_compiles_with_maven(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if shutil.which("mvn") is None:
        pytest.skip("mvn is not installed")

    canonical_model, summary, raw_spec = _stripe_model()
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    workspace = generator_service.generate("pytest-maven-run", canonical_model, summary, raw_spec)

    subprocess.run(
        ["mvn", "-q", "-DskipTests", "package"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
