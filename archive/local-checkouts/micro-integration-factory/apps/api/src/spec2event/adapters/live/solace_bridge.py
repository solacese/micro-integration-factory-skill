from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from spec2event.db import session_scope
from spec2event.services.run_service import record_event_log


class SolaceLiveBridgeManager:
    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._lock = threading.Lock()

    def ensure_subscription(
        self, run_id: str, topics: list[str], credentials: dict[str, str]
    ) -> None:
        if not topics or not all(credentials.values()):
            return
        with self._lock:
            existing = self._processes.get(run_id)
            if existing and existing.poll() is None:
                existing.terminate()
            process = subprocess.Popen(
                ["node", str(_bridge_script_path())],
                cwd=str(_repo_root()),
                env={
                    **_minimal_env(),
                    "SPEC2EVENT_RUN_ID": run_id,
                    "SOLACE_TOPICS_JSON": json.dumps(topics),
                    "SOLACE_BROKER_URL": credentials["solace_broker_url"],
                    "SOLACE_VPN": credentials["solace_vpn"],
                    "SOLACE_USERNAME": credentials["solace_username"],
                    "SOLACE_PASSWORD": credentials["solace_password"],
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            self._processes[run_id] = process
            thread = threading.Thread(
                target=self._read_output,
                args=(run_id, process),
                daemon=True,
                name=f"solace-bridge-{run_id}",
            )
            thread.start()

    def _read_output(self, run_id: str, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") != "message":
                continue
            with session_scope() as db:
                run = db.get(
                    __import__("spec2event.models", fromlist=["GenerationRun"]).GenerationRun,
                    run_id,
                )
                if run is None:
                    continue
                record_event_log(
                    db,
                    run,
                    correlation_id=payload.get("correlationId") or "unknown",
                    stage="event_consumed",
                    topic_name=payload.get("topicName"),
                    payload_json=payload.get("payload"),
                )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _bridge_script_path() -> Path:
    return (
        _repo_root()
        / "apps"
        / "api"
        / "src"
        / "spec2event"
        / "adapters"
        / "live"
        / "solace_bridge_node.js"
    )


def _minimal_env() -> dict[str, str]:
    import os

    return os.environ.copy()


live_bridge_manager = SolaceLiveBridgeManager()
