from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from spec2event.db import SessionLocal, session_scope
from spec2event.models import CapturedEvent
from spec2event.services.builder_service import serialize_captured_event


@dataclass
class SubscriptionState:
    id: str
    topic_filter: str
    status: str
    message: str
    process: subprocess.Popen[str] | None = None


class SolaceCaptureManager:
    def __init__(self) -> None:
        self._subscriptions: dict[str, SubscriptionState] = {}
        self._lock = threading.Lock()

    def start(
        self,
        db: Session,
        *,
        broker_url: str,
        vpn: str,
        username: str,
        password: str,
        topic_filter: str,
    ) -> SubscriptionState:
        missing = [
            name
            for name, value in {
                "broker_url": broker_url,
                "vpn": vpn,
                "username": username,
                "password": password,
                "topic_filter": topic_filter,
            }.items()
            if not value
        ]
        if missing:
            raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")

        subscription_id = str(uuid.uuid4())
        state = SubscriptionState(
            id=subscription_id,
            topic_filter=topic_filter,
            status="connecting",
            message="Starting Solace capture",
        )
        with self._lock:
            self._subscriptions[subscription_id] = state

        if broker_url.startswith("demo://"):
            self._record_demo_event(db, subscription_id, broker_url, topic_filter)
            state.status = "running"
            state.message = "Demo event captured"
            return state

        script = _capture_script_path()
        if not script.exists():
            state.status = "failed"
            state.message = "Solace capture script was not found"
            return state
        try:
            process = subprocess.Popen(
                ["node", str(script)],
                cwd=str(_repo_root()),
                env={
                    **os.environ,
                    "MIF_SUBSCRIPTION_ID": subscription_id,
                    "SOLACE_TOPIC_FILTER": topic_filter,
                    "SOLACE_BROKER_URL": broker_url,
                    "SOLACE_VPN": vpn,
                    "SOLACE_USERNAME": username,
                    "SOLACE_PASSWORD": password,
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            state.status = "failed"
            state.message = "Node.js is required for live Solace capture"
            return state

        state.process = process
        state.status = "running"
        state.message = "Listening for Solace messages"
        thread = threading.Thread(
            target=self._read_process_output,
            args=(state, process, broker_url, topic_filter),
            daemon=True,
            name=f"solace-capture-{subscription_id}",
        )
        thread.start()
        return state

    def get(self, subscription_id: str) -> SubscriptionState | None:
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def _record_demo_event(
        self, db: Session, subscription_id: str, broker_url: str, topic_filter: str
    ) -> None:
        payload = {
            "orderId": "ORD-10042",
            "customer": {"id": "C-7781", "tier": "gold"},
            "amount": 129.95,
            "currency": "USD",
            "status": "created",
        }
        event = CapturedEvent(
            subscription_id=subscription_id,
            broker_url=broker_url,
            topic_filter=topic_filter,
            topic_name="orders/created/v1",
            headers_json={"source": "demo"},
            payload_json=payload,
        )
        db.add(event)
        db.flush()

    def _read_process_output(
        self,
        state: SubscriptionState,
        process: subprocess.Popen[str],
        broker_url: str,
        topic_filter: str,
    ) -> None:
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
            if payload.get("type") == "ready":
                state.status = "running"
                state.message = "Listening for Solace messages"
                continue
            if payload.get("type") == "error":
                state.status = "failed"
                state.message = payload.get("info") or "Solace capture failed"
                continue
            if payload.get("type") != "message":
                continue
            with session_scope() as db:
                event = CapturedEvent(
                    subscription_id=state.id,
                    broker_url=broker_url,
                    topic_filter=topic_filter,
                    topic_name=payload.get("topicName") or topic_filter,
                    headers_json=payload.get("headers") or {},
                    payload_json=_safe_payload(payload.get("payload")),
                )
                db.add(event)


def events_for_subscription(db: Session, subscription_id: str) -> list[dict[str, Any]]:
    events = (
        db.query(CapturedEvent)
        .filter(CapturedEvent.subscription_id == subscription_id)
        .order_by(CapturedEvent.created_at.asc())
        .all()
    )
    return [serialize_captured_event(event) for event in events]


def stream_subscription_events(subscription_id: str):
    seen: set[str] = set()
    while True:
        with SessionLocal() as db:
            events = (
                db.query(CapturedEvent)
                .filter(CapturedEvent.subscription_id == subscription_id)
                .order_by(CapturedEvent.created_at.asc())
                .all()
            )
            for event in events:
                if event.id in seen:
                    continue
                seen.add(event.id)
                yield f"data: {json.dumps(serialize_captured_event(event))}\n\n"
        time.sleep(1)


def _safe_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"data": value}


def _repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (
            parent
            / "apps"
            / "api"
            / "src"
            / "spec2event"
            / "adapters"
            / "live"
            / "solace_capture_node.js"
        ).exists():
            return parent
    return current.parents[5]


def _capture_script_path() -> Path:
    return (
        _repo_root()
        / "apps"
        / "api"
        / "src"
        / "spec2event"
        / "adapters"
        / "live"
        / "solace_capture_node.js"
    )


capture_manager = SolaceCaptureManager()
