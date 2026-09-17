from __future__ import annotations


class LiveEventBridge:
    def ensure_subscription(
        self, run_id: str, topics: list[str], credentials: dict[str, str]
    ) -> None:
        raise NotImplementedError
