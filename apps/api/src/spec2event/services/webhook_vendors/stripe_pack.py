"""Stripe webhook event pack.

Extracts the hardcoded Stripe detection and event synthesis from
openapi_service.py into a pluggable vendor event pack.
"""

from __future__ import annotations

from typing import Any

from spec2event.services.webhook_vendors.base import VendorEventPack


class StripeEventPack(VendorEventPack):
    """Stripe webhook vendor event pack."""

    def __init__(self) -> None:
        super().__init__(
            vendor_id="stripe",
            display_name="Stripe",
            detection_keywords=["stripe"],
            signature_verification=True,
        )

    def event_candidates(
        self, domain: str, application_name: str
    ) -> list[dict[str, Any]]:
        """Return Stripe's canonical webhook event types."""
        return [
            {
                "canonicalEventName": "StripePaymentIntentSucceeded",
                "topicName": f"{domain}/stripe/payment_intent/succeeded/v1",
                "schemaName": "StripePaymentIntentSucceededPayload",
                "applicationName": application_name,
            },
            {
                "canonicalEventName": "StripePaymentIntentFailed",
                "topicName": f"{domain}/stripe/payment_intent/failed/v1",
                "schemaName": "StripePaymentIntentFailedPayload",
                "applicationName": application_name,
            },
            {
                "canonicalEventName": "StripeChargeRefunded",
                "topicName": f"{domain}/stripe/charge/refunded/v1",
                "schemaName": "StripeChargeRefundedPayload",
                "applicationName": application_name,
            },
        ]

    def infer_action(
        self, method: str, operation_id: str, summary: str, entity: str
    ) -> str | None:
        """Stripe-specific action inference."""
        text = f"{operation_id} {summary}".lower()
        if "refund" in text:
            return "refunded"
        return None
