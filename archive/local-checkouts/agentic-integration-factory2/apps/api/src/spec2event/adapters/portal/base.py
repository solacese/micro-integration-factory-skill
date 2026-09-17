from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PortalSyncItem:
    artifact_type: str
    artifact_name: str
    status: str
    external_id: str | None = None
    manual_action: str | None = None
    request_payload: dict | None = None
    response_payload: dict | None = None


@dataclass
class PortalSyncResult:
    status: str
    message: str
    items: list[PortalSyncItem] = field(default_factory=list)


class PortalSyncAdapter:
    def sync(self, canonical_model: dict) -> PortalSyncResult:
        raise NotImplementedError
