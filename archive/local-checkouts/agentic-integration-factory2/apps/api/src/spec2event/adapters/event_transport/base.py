from __future__ import annotations


class EventTransportAdapter:
    def is_configured(self) -> bool:
        raise NotImplementedError
