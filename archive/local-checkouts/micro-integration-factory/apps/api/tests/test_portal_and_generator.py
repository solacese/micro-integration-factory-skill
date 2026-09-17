from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from spec2event.adapters.portal.solace_event_portal import SolaceEventPortalAdapter
from spec2event.config import get_settings
from spec2event.services.generator_service import generator_service
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)

API_ROOT = Path(__file__).resolve().parents[1]
STRIPE_SPEC = API_ROOT / "resources" / "samples" / "openapi" / "stripe-webhook-demo.yaml"


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
        == {
            "name": "StripePaymentIntentSucceeded",
            "topicName": "payments/stripe/payment_intent/succeeded/v1",
            "schemaName": "StripePaymentIntentSucceededPayload",
        }
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
    schema_version_payloads = [
        payload
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/schemaVersions")
    ]
    assert schema_version_payloads
    assert all(isinstance(payload["content"], str) for payload in schema_version_payloads)
    event_names = [
        payload["name"]
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/events")
    ]
    assert "StripePaymentIntentSucceeded" in event_names
    event_version_payloads = [
        payload
        for method, endpoint, payload, _ in calls
        if method == "POST" and endpoint.endswith("/eventVersions")
    ]
    assert event_version_payloads
    assert event_version_payloads[0]["deliveryDescriptor"]["brokerType"] == "solace"
    flow_patch = next(
        payload
        for method, endpoint, payload, _ in calls
        if method == "PATCH" and "/applicationVersions/" in endpoint
    )
    assert flow_patch["declaredProducedEventVersionIds"]


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
