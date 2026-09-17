"""Webhook vendor event packs.

A vendor event pack provides:
- Detection: given an OpenAPI spec, detect if this vendor's webhook format is present
- Event synthesis: produce canonical event candidates from the vendor's known event types
- Signature verification: optional webhook signature verification capability

This is the generic replacement for the hardcoded Stripe logic. Any SaaS
vendor (Stripe, Twilio, GitHub, Shopify, etc.) can be supported by adding
a new event pack without modifying the core OpenAPI canonicalization logic.
"""

from spec2event.services.webhook_vendors.base import (
    VendorEventPack,
    detect_vendor,
    get_vendor_pack,
    register_vendor_pack,
)
from spec2event.services.webhook_vendors.stripe_pack import StripeEventPack

# Register built-in vendor packs
register_vendor_pack(StripeEventPack())

__all__ = [
    "VendorEventPack",
    "detect_vendor",
    "get_vendor_pack",
    "register_vendor_pack",
]
