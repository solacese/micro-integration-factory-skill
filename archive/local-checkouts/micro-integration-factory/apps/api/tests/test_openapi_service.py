from __future__ import annotations

from pathlib import Path

from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)

API_ROOT = Path(__file__).resolve().parents[1]
STRIPE_SPEC = API_ROOT / "resources" / "samples" / "openapi" / "stripe-webhook-demo.yaml"


def test_summarize_openapi_extracts_service_metadata() -> None:
    document = load_openapi_document(STRIPE_SPEC.read_text(encoding="utf-8"))

    summary = summarize_openapi(document)

    assert summary["title"] == "Stripe Payments Gateway"
    assert summary["serviceName"] == "stripe-payments-gateway"
    assert summary["operationCount"] >= 2


def test_canonicalize_openapi_derives_expected_stripe_topics() -> None:
    document = load_openapi_document(STRIPE_SPEC.read_text(encoding="utf-8"))

    canonical_model = canonicalize_openapi(document)

    assert canonical_model["stripeEnabled"] is True
    assert "payments/stripe/payment_intent/succeeded/v1" in canonical_model["topics"]
    assert "payments/stripe/payment_intent/failed/v1" in canonical_model["topics"]
    assert "StripePaymentIntentSucceededPayload" in canonical_model["schemaNames"]
    assert canonical_model["applicationNames"] == ["stripe-payments-gateway-integration"]
    assert canonical_model["testFixtures"]
    assert canonical_model["testFixtures"][0]["payload"]


def test_canonicalize_openapi_resolves_path_parameters_in_test_fixtures() -> None:
    document = {
        "openapi": "3.0.3",
        "info": {"title": "Path Demo", "version": "1.0.0"},
        "paths": {
            "/pets/{petId}": {
                "post": {
                    "operationId": "updatePet",
                    "summary": "Update pet",
                    "tags": ["pets"],
                    "parameters": [
                        {
                            "name": "petId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    canonical_model = canonicalize_openapi(document)

    assert canonical_model["testFixtures"] == [
        {
            "operationId": "updatePet",
            "label": "POST /pets/{petId}",
            "method": "POST",
            "path": "/pets/1",
            "payload": {"name": "string"},
        }
    ]
