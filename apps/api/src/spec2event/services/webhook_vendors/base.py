"""Base class and registry for webhook vendor event packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VendorEventPack:
    """A webhook vendor event pack declares how to detect and synthesize events.

    Subclass to add support for a new SaaS vendor's webhook format.
    """

    vendor_id: str  # e.g. "stripe", "github", "twilio"
    display_name: str = ""
    detection_keywords: list[str] = field(default_factory=list)
    signature_verification: bool = False

    def detect(self, spec_text: str, paths: list[str], tags: list[str]) -> bool:
        """Return True if this vendor's webhook format is detected.

        Default implementation: keyword match against spec text, paths, tags.
        """
        joined = " ".join([spec_text, *paths, *tags]).lower()
        return any(keyword in joined for keyword in self.detection_keywords)

    def event_candidates(
        self, domain: str, application_name: str
    ) -> list[dict[str, Any]]:
        """Return the canonical event candidates for this vendor.

        Override to provide vendor-specific event types.
        """
        return []

    def infer_action(
        self, method: str, operation_id: str, summary: str, entity: str
    ) -> str | None:
        """Override action inference for vendor-specific patterns.

        Return None to fall back to generic inference.
        """
        return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_VENDOR_REGISTRY: dict[str, VendorEventPack] = {}


def register_vendor_pack(pack: VendorEventPack) -> None:
    """Register a vendor event pack."""
    _VENDOR_REGISTRY[pack.vendor_id] = pack


def get_vendor_pack(vendor_id: str) -> VendorEventPack | None:
    """Look up a vendor pack by ID."""
    return _VENDOR_REGISTRY.get(vendor_id)


def detect_vendor(
    spec_text: str, paths: list[str], tags: list[str]
) -> VendorEventPack | None:
    """Detect which vendor (if any) matches the given spec/paths/tags.

    Returns the first matching vendor pack, or None if no vendor detected.
    """
    for pack in _VENDOR_REGISTRY.values():
        if pack.detect(spec_text, paths, tags):
            return pack
    return None
