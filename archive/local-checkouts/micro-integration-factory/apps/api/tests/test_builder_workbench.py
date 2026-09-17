from __future__ import annotations

import json as json_module
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from spec2event.config import get_settings
from spec2event.db import Base, get_db
from spec2event.main import app
from spec2event.services import solace_capture_service as capture_service
from spec2event.services.solace_capture_service import (
    SolaceCaptureManager,
    _capture_script_path,
)


def test_builder_workbench_demo_flow(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "claude-sonnet-4-6")
    get_settings.cache_clear()

    litellm_calls: list[str] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt = json["messages"][1]["content"]
        prompt_payload = json_module.loads(prompt)
        litellm_calls.append(prompt_payload["intent"])
        if prompt_payload["intent"] == "chat_turn":
            assert prompt_payload["previousDraft"] is not None
        language = prompt_payload["transformLanguage"]
        file_path = {
            "dataweave": "src/main/resources/transforms/transform.dwl",
            "groovy": "src/main/resources/transforms/transform.groovy",
            "java_sdk": "src/main/resources/transforms/transform.md",
        }[language]
        file_content = {
            "dataweave": "%dw 2.0\noutput application/json\n---\npayload",
            "groovy": (
                "def transform(Map payload) { "
                "return payload + [sourceTopic: 'orders/created/v1'] }"
            ),
            "java_sdk": (
                "Use Jackson ObjectNode to map the captured payload "
                "to the canonical event."
            ),
        }[language]
        draft = {
            "transformLanguage": language,
            "intentSummary": "Map the order payload to a canonical order-created event.",
            "assistantMessage": "Designed the micro integration with inferred defaults.",
            "qualifyingQuestions": [
                "Should invalid order payloads be rejected or routed to an error topic?"
            ],
            "topicMapping": {
                "inputTopic": "orders/created/v1",
                "outputTopic": "orders/canonical/created/v1",
            },
            "sampleOutput": {
                "sourceTopic": "orders/created/v1",
                "orderId": "ORD-1001",
                "status": "created",
            },
            "files": [
                {
                    "path": file_path,
                    "purpose": "Generated transform artifact",
                    "content": file_content,
                }
            ],
            "validationNotes": ["Invalid payloads are rejected by default."],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        subscription_response = client.post(
            "/api/solace/subscriptions",
            headers=admin_headers,
            json={
                "brokerUrl": "demo://sample",
                "vpn": "default",
                "username": "demo",
                "password": "demo",
                "topicFilter": "orders/>",
            },
        )
        assert subscription_response.status_code == 200
        subscription_id = subscription_response.json()["id"]

        events_response = client.get(
            f"/api/solace/subscriptions/{subscription_id}/captured-events"
        )
        assert events_response.status_code == 200
        captured_event = events_response.json()[0]
        assert captured_event["topicName"] == "orders/created/v1"

        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": captured_event["id"],
                "transformLanguage": "dataweave",
            },
        )
        assert session_response.status_code == 200
        builder_session = session_response.json()
        assert builder_session["status"] == "awaiting_design"
        assert builder_session["draft"] is None

        design_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/design",
            headers=admin_headers,
            json={
                "content": "Design this as a DataWeave mapping first.",
                "transformLanguage": "dataweave",
            },
        )
        assert design_response.status_code == 200
        builder_session = design_response.json()
        assert builder_session["draft"]["transformLanguage"] == "dataweave"
        assert builder_session["draft"]["qualifyingQuestions"] == []
        assert builder_session["messages"] == []

        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": "Map the order payload to a canonical order-created event.",
                "transformLanguage": "groovy",
            },
        )
        assert message_response.status_code == 200
        assert message_response.json()["transformLanguage"] == "groovy"

        preview_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/preview",
            headers=admin_headers,
        )
        assert preview_response.status_code == 200
        assert preview_response.json()["sampleOutput"]["sourceTopic"] == "orders/created/v1"
        assert litellm_calls == ["live_design", "chat_turn"]

        generate_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        assert litellm_calls == ["live_design", "chat_turn"]
        body = generate_response.json()
        assert body["run"]["status"] == "completed"
        assert body["workerJob"]["status"] == "pending"
        assert body["session"]["draft"]["generationMode"] == "fast_template_single_transform_file"

        artifact_response = client.get(f"/api/runs/{body['run']['id']}/artifacts")
        assert artifact_response.status_code == 200
        artifact_paths = {artifact["path"] for artifact in artifact_response.json()}
        assert "ai/claude-code-plan.json" in artifact_paths
        assert ".dockerignore" in artifact_paths
        assert ".env.example" in artifact_paths
        assert "docs/micro-integration.md" in artifact_paths
        assert "docs/event-portal-schema.md" in artifact_paths
        assert "docs/operations.md" in artifact_paths
        assert "event-portal/event-api.json" in artifact_paths
        assert "helm/templates/pdb.yaml" in artifact_paths
        assert "orders-canonical-created-v1.code-workspace" in artifact_paths
        assert ".vscode/settings.json" in artifact_paths
        assert ".vscode/extensions.json" in artifact_paths
        assert ".vscode/launch.json" in artifact_paths
        assert "src/main/resources/transforms/transform.groovy" in artifact_paths
        assert "src/main/resources/transforms/sample-output.json" in artifact_paths
        archive_response = client.get(f"/api/runs/{body['run']['id']}/workspace.zip")
        assert archive_response.status_code == 200
        with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
            names = set(archive.namelist())
        assert "pom.xml" in names
        assert "Dockerfile" in names
        assert ".dockerignore" in names
        assert ".env.example" in names
        assert "docs/micro-integration.md" in names
        assert "event-portal/event-api.json" in names
        assert "orders-canonical-created-v1.code-workspace" in names
        assert "src/main/resources/transforms/transform.groovy" in names

        transform_response = client.get(f"/api/runs/{body['run']['id']}/transform-file")
        assert transform_response.status_code == 200
        assert b"def transform(Map payload)" in transform_response.content
        assert "attachment" in transform_response.headers["content-disposition"]

        image_result_response = client.post(
            f"/api/worker/jobs/{body['workerJob']['id']}/result",
            headers=admin_headers,
            json={
                "status": "completed",
                "logs": "Docker image built.\n",
                "imageTag": "micro-integration-factory/test-export:local",
                "projectPath": body["workerJob"]["projectPath"],
                "result": {"dockerAvailable": True, "imageSizeBytes": 2048},
            },
        )
        assert image_result_response.status_code == 200

        def mock_docker_run(command, **kwargs):  # noqa: ANN001
            del kwargs
            if command[:3] == ["/usr/bin/docker", "image", "inspect"]:
                stdout = '[{"Id":"sha256:test"}]'
                return type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()
            if command[:3] == ["/usr/bin/docker", "save", "-o"]:
                Path(command[3]).write_bytes(b"docker-image-tar")
                return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return type("Result", (), {"returncode": 1, "stdout": "", "stderr": "bad command"})()

        monkeypatch.setattr("spec2event.api.routes.shutil.which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr("spec2event.api.routes.subprocess.run", mock_docker_run)
        image_response = client.get(f"/api/runs/{body['run']['id']}/image.tar")
        assert image_response.status_code == 200
        assert image_response.content == b"docker-image-tar"
        assert "attachment" in image_response.headers["content-disposition"]
    finally:
        app.dependency_overrides.clear()


def test_builder_requires_litellm_for_chat(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        subscription_response = client.post(
            "/api/solace/subscriptions",
            headers=admin_headers,
            json={
                "brokerUrl": "demo://sample",
                "vpn": "default",
                "username": "demo",
                "password": "demo",
                "topicFilter": "orders/>",
            },
        )
        captured_event = client.get(
            f"/api/solace/subscriptions/{subscription_response.json()['id']}/captured-events"
        ).json()[0]
        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": captured_event["id"],
                "transformLanguage": "java_sdk",
            },
        )
        builder_session = session_response.json()
        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": (
                    "Anonymize PII and only return customer, items, total, and orderId."
                ),
                "transformLanguage": "java_sdk",
            },
        )
        assert message_response.status_code == 400
        assert "LiteLLM is required for every builder chat turn" in message_response.text
    finally:
        app.dependency_overrides.clear()


def test_builder_repairs_malformed_litellm_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs-repair"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "bedrock-claude-4-5-sonnet")
    get_settings.cache_clear()

    calls: list[dict] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        calls.append(json)
        if len(calls) == 1:
            content = '{"transformLanguage": "java_sdk", "intentSummary": "bad'
        else:
            repair_prompt = json_module.loads(json["messages"][1]["content"])
            assert "invalidResponse" in repair_prompt
            draft = {
                "transformLanguage": "java_sdk",
                "intentSummary": "Map the payload after JSON repair.",
                "assistantMessage": "Repaired the draft and wrote transform.md.",
                "qualifyingQuestions": [],
                "topicMapping": {
                    "inputTopic": "orders/created/v1",
                    "outputTopic": "orders/repaired/v1",
                },
                "sampleOutput": {"orderId": "ORD-1001", "status": "created"},
                "files": [
                    {
                        "path": "src/main/resources/transforms/transform.md",
                        "purpose": "Generated transform artifact",
                        "content": "Map the payload after JSON repair.",
                    }
                ],
                "validationNotes": ["Malformed JSON was repaired automatically."],
            }
            content = json_module.dumps(draft)

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": content}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        subscription_response = client.post(
            "/api/solace/subscriptions",
            headers=admin_headers,
            json={
                "brokerUrl": "demo://sample",
                "vpn": "default",
                "username": "demo",
                "password": "demo",
                "topicFilter": "orders/>",
            },
        )
        captured_event = client.get(
            f"/api/solace/subscriptions/{subscription_response.json()['id']}/captured-events"
        ).json()[0]
        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": captured_event["id"],
                "transformLanguage": "java_sdk",
            },
        )
        builder_session = session_response.json()
        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": "Create a robust transformation draft.",
                "transformLanguage": "java_sdk",
            },
        )
        assert message_response.status_code == 200
        assert len(calls) == 2
        draft = message_response.json()["draft"]
        assert draft["topicMapping"]["outputTopic"] == "orders/repaired/v1"
        assert draft["llmProvider"]["provider"] == "litellm"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("language", "expected_path"),
    [
        ("java_sdk", "src/main/resources/transforms/transform.md"),
        ("groovy", "src/main/resources/transforms/transform.groovy"),
        ("dataweave", "src/main/resources/transforms/transform.dwl"),
    ],
)
def test_builder_generates_three_transform_options(
    monkeypatch, tmp_path: Path, language: str, expected_path: str
) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / f"generated-runs-{language}"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "claude-sonnet-4-6")
    get_settings.cache_clear()

    seen_schema_contexts: list[str | None] = []
    litellm_intents: list[str] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt_payload = json_module.loads(json["messages"][1]["content"])
        seen_schema_contexts.append(prompt_payload.get("schemaContext"))
        litellm_intents.append(prompt_payload["intent"])
        language_value = prompt_payload["transformLanguage"]
        content = {
            "java_sdk": "Map keep fields with Jackson ObjectNode.",
            "groovy": (
                "def transform(Map payload) { "
                "return payload.subMap(['orderId','customer','items','total']) }"
            ),
            "dataweave": (
                "%dw 2.0\n"
                "output application/json\n"
                "---\n"
                "{ orderId: payload.orderId, customer: payload.customer, "
                "items: payload.items, total: payload.total }"
            ),
        }[language_value]
        draft = {
            "transformLanguage": language_value,
            "intentSummary": (
                "Strip sensitive order fields and keep customer, items, total, orderId."
            ),
            "assistantMessage": "Generated the transform-only artifact with inferred defaults.",
            "qualifyingQuestions": [],
            "topicMapping": {
                "inputTopic": "orders/created/v1",
                "outputTopic": "orders/public/created/v1",
            },
            "sampleOutput": {
                "orderId": "ORD-1001",
                "customer": {"id": "C-100"},
                "items": [{"sku": "SKU-1"}],
                "total": 42.5,
            },
            "files": [
                {
                    "path": expected_path,
                    "purpose": "Generated transform artifact",
                    "content": content,
                }
            ],
            "validationNotes": ["Schema keep rule respected."],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        subscription_response = client.post(
            "/api/solace/subscriptions",
            headers=admin_headers,
            json={
                "brokerUrl": "demo://sample",
                "vpn": "default",
                "username": "demo",
                "password": "demo",
                "topicFilter": "orders/>",
            },
        )
        captured_event = client.get(
            f"/api/solace/subscriptions/{subscription_response.json()['id']}/captured-events"
        ).json()[0]
        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": captured_event["id"],
                "transformLanguage": language,
            },
        )
        builder_session = session_response.json()
        design_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/design",
            headers=admin_headers,
            json={
                "content": (
                    "Strip out sensitive data from ORDER and only return customer, "
                    "items and total."
                ),
                "transformLanguage": language,
                "schemaContext": '{"keep": ["customer", "items", "total", "orderId"]}',
            },
        )
        assert design_response.status_code == 200
        assert design_response.json()["draft"]["schemaContext"] is not None
        assert design_response.json()["draft"]["qualifyingQuestions"] == []
        generate_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        body = generate_response.json()
        assert litellm_intents == ["live_design"]
        assert body["session"]["draft"]["generationMode"] == "fast_template_single_transform_file"
        artifact_response = client.get(f"/api/runs/{body['run']['id']}/artifacts")
        artifact_paths = {artifact["path"] for artifact in artifact_response.json()}
        assert expected_path in artifact_paths
        assert any(context and "keep" in context for context in seen_schema_contexts)
    finally:
        app.dependency_overrides.clear()


def test_builder_generates_protocol_change_micro_integration(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs-protocol"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "bedrock-claude-4-5-sonnet")
    get_settings.cache_clear()

    seen_prompt_payloads: list[dict] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt_payload = json_module.loads(json["messages"][1]["content"])
        seen_prompt_payloads.append(prompt_payload)
        assert prompt_payload["protocolChangeBehavior"]["incomingExamples"]
        assert prompt_payload["protocolChangeBehavior"]["targetExamples"]
        assert "MQTT inbound message" in prompt_payload["userPrompt"]
        assert "Parquet" in prompt_payload["userPrompt"]

        draft = {
            "transformLanguage": "java_sdk",
            "intentSummary": "Convert MQTT order payloads into a Parquet-ready event.",
            "assistantMessage": (
                "Wrote transform.md for MQTT to Parquet, publishing to "
                "protocol/parquet/orders/created/v1 with a compact sample output."
            ),
            "qualifyingQuestions": [],
            "topicMapping": {
                "inputTopic": "orders/created/v1",
                "outputTopic": "protocol/parquet/orders/created/v1",
            },
            "sampleOutput": {
                "sourceProtocol": "MQTT",
                "targetFormat": "Parquet",
                "topic": "protocol/parquet/orders/created/v1",
                "schema": {
                    "orderId": "string",
                    "customerId": "string",
                    "total": "double",
                },
                "rows": [
                    {
                        "orderId": "ORD-1001",
                        "customerId": "C-100",
                        "total": 42.5,
                    }
                ],
            },
            "files": [
                {
                    "path": "src/main/resources/transforms/transform.md",
                    "purpose": "Protocol-change transform artifact",
                    "content": (
                        "# MQTT to Parquet transform\n\n"
                        "Read MQTT topic and payload metadata, validate required order "
                        "fields, and emit a Parquet-ready record set for "
                        "protocol/parquet/orders/created/v1."
                    ),
                }
            ],
            "validationNotes": [
                "Assumed MQTT topic metadata is preserved as source correlation context.",
                "Assumed the generated MDK scaffold handles broker connectivity.",
            ],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        subscription_response = client.post(
            "/api/solace/subscriptions",
            headers=admin_headers,
            json={
                "brokerUrl": "demo://sample",
                "vpn": "default",
                "username": "demo",
                "password": "demo",
                "topicFilter": "orders/>",
            },
        )
        assert subscription_response.status_code == 200
        captured_event = client.get(
            f"/api/solace/subscriptions/{subscription_response.json()['id']}/captured-events"
        ).json()[0]
        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": captured_event["id"],
                "transformLanguage": "java_sdk",
            },
        )
        builder_session = session_response.json()
        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": (
                    "Create a protocol-change micro integration. Treat the captured "
                    "event as an MQTT inbound message and convert the payload into "
                    "Parquet. Infer the output topic, field mappings, type conversions, "
                    "and metadata rules."
                ),
                "transformLanguage": "java_sdk",
            },
        )
        assert message_response.status_code == 200
        draft = message_response.json()["draft"]
        assert draft["llmProvider"]["provider"] == "litellm"
        assert draft["llmProvider"]["model"] == "bedrock-claude-4-5-sonnet"
        assert draft["qualifyingQuestions"] == []
        assert draft["topicMapping"]["outputTopic"] == "protocol/parquet/orders/created/v1"
        assert draft["sampleOutput"]["targetFormat"] == "Parquet"

        generate_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        body = generate_response.json()
        assert body["run"]["status"] == "completed"
        assert body["session"]["draft"]["generationMode"] == "fast_template_single_transform_file"
        assert len(seen_prompt_payloads) == 1

        artifact_response = client.get(f"/api/runs/{body['run']['id']}/artifacts")
        artifact_paths = {artifact["path"] for artifact in artifact_response.json()}
        assert "src/main/resources/transforms/transform.md" in artifact_paths

        archive_response = client.get(f"/api/runs/{body['run']['id']}/workspace.zip")
        assert archive_response.status_code == 200
        with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
            transform_content = archive.read(
                "src/main/resources/transforms/transform.md"
            ).decode()
        assert "MQTT to Parquet" in transform_content
        assert "protocol/parquet/orders/created/v1" in transform_content
    finally:
        app.dependency_overrides.clear()


def test_builder_generates_system_message_to_event_micro_integration(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs-system-message"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "bedrock-claude-4-5-sonnet")
    get_settings.cache_clear()

    seen_prompt_payloads: list[dict] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt_payload = json_module.loads(json["messages"][1]["content"])
        seen_prompt_payloads.append(prompt_payload)
        assert prompt_payload["inputMessage"]["sourceType"] == "manual_input"
        assert prompt_payload["inputMessage"]["inputFormat"] == "edifact"
        assert "systemToEventBehavior" in prompt_payload
        assert "DESADV" in prompt_payload["inputMessage"]["payload"]["rawPayload"]

        draft = {
            "transformLanguage": "dataweave",
            "intentSummary": "Convert supplier DESADV notices into shipment events.",
            "assistantMessage": (
                "Wrote transform.dwl for the EDIFACT notice and publish "
                "shipment events to canonical/shipment/advanced-notice/v1."
            ),
            "qualifyingQuestions": [],
            "topicMapping": {
                "inputTopic": "systems/volvo/desadv/v1",
                "outputTopic": "canonical/shipment/advanced-notice/v1",
            },
            "sampleOutput": {
                "eventType": "ShipmentAdvancedNotice",
                "supplier": "VOLVO",
                "shipmentId": "DESADV-1",
                "status": "announced",
            },
            "files": [
                {
                    "path": "src/main/resources/transforms/transform.dwl",
                    "purpose": "DataWeave system-to-event transform",
                    "content": (
                        "%dw 2.0\n"
                        "output application/json\n"
                        "---\n"
                        "{ eventType: 'ShipmentAdvancedNotice', "
                        "shipmentId: 'DESADV-1', status: 'announced' }"
                    ),
                }
            ],
            "validationNotes": [
                "Assumed supplied EDIFACT DESADV schema maps BGM to shipmentId."
            ],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        input_response = client.post(
            "/api/builder/input-events",
            headers=admin_headers,
            json={
                "sourceName": "Volvo supplier EDI gateway",
                "topicName": "systems/volvo/desadv/v1",
                "inputFormat": "edifact",
                "payload": "UNH+1+DESADV:D:96A:UN+BGM+351+DESADV-1+9'",
            },
        )
        assert input_response.status_code == 200
        input_event = input_response.json()
        assert input_event["headers"]["sourceType"] == "manual_input"
        assert input_event["payload"]["inputFormat"] == "edifact"

        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": input_event["id"],
                "transformLanguage": "dataweave",
            },
        )
        assert session_response.status_code == 200
        builder_session = session_response.json()

        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": (
                    "Use the supplied EDIFACT DESADV message as the input from a "
                    "supplier system and publish a clean shipment advanced notice event."
                ),
                "transformLanguage": "dataweave",
            },
        )
        assert message_response.status_code == 200
        draft = message_response.json()["draft"]
        assert draft["topicMapping"]["outputTopic"] == (
            "canonical/shipment/advanced-notice/v1"
        )
        assert draft["sampleOutput"]["eventType"] == "ShipmentAdvancedNotice"

        generate_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        body = generate_response.json()
        assert body["run"]["status"] == "completed"
        assert body["run"]["canonicalModel"]["topics"] == [
            "canonical/shipment/advanced-notice/v1"
        ]
        assert len(seen_prompt_payloads) == 1

        artifact_response = client.get(f"/api/runs/{body['run']['id']}/artifacts")
        artifact_paths = {artifact["path"] for artifact in artifact_response.json()}
        assert "src/main/resources/transforms/transform.dwl" in artifact_paths

        archive_response = client.get(f"/api/runs/{body['run']['id']}/workspace.zip")
        assert archive_response.status_code == 200
        with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
            sample_input = archive.read(
                "src/main/resources/transforms/sample-input.json"
            ).decode()
        assert "DESADV" in sample_input
    finally:
        app.dependency_overrides.clear()


def test_builder_generates_uns_topic_header_rewrite(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs-uns-rewrite"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.setenv("LITELLM_BASE_URL", "https://litellm.test")
    monkeypatch.setenv("LITELLM_API_KEY", "test-key")
    monkeypatch.setenv("LITELLM_MODEL", "bedrock-claude-4-5-sonnet")
    get_settings.cache_clear()

    seen_prompt_payloads: list[dict] = []

    def mock_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt_payload = json_module.loads(json["messages"][1]["content"])
        seen_prompt_payloads.append(prompt_payload)
        assert "headerRewriteBehavior" in prompt_payload
        assert prompt_payload["inputMessage"]["headers"]["topic"] == (
            "spBv1.0/plant1/DDATA/line7/compressor42"
        )

        draft = {
            "transformLanguage": "dataweave",
            "intentSummary": "Rewrite Sparkplug telemetry to a UNS topic and headers.",
            "assistantMessage": (
                "Wrote transform.dwl to publish compressor telemetry to "
                "uns/site-a/line-7/compressor-42/telemetry/v1 and update the topic header."
            ),
            "qualifyingQuestions": [],
            "topicMapping": {
                "inputTopic": "sparkplug/plant1/line7/compressor42",
                "outputTopic": "uns/site-a/line-7/compressor-42/telemetry/v1",
            },
            "headerMapping": {
                "inputHeaders": {
                    "topic": "spBv1.0/plant1/DDATA/line7/compressor42",
                    "correlationId": "corr-42",
                },
                "outputHeaders": {
                    "topic": "uns/site-a/line-7/compressor-42/telemetry/v1",
                    "sourceTopic": "spBv1.0/plant1/DDATA/line7/compressor42",
                    "correlationId": "corr-42",
                },
                "topicHeader": "uns/site-a/line-7/compressor-42/telemetry/v1",
                "notes": ["Preserved correlationId and retained original sourceTopic."],
            },
            "sampleOutput": {
                "headers": {
                    "topic": "uns/site-a/line-7/compressor-42/telemetry/v1",
                    "sourceTopic": "spBv1.0/plant1/DDATA/line7/compressor42",
                    "correlationId": "corr-42",
                },
                "payload": {
                    "assetId": "compressor-42",
                    "temperatureC": 74.2,
                    "pressureBar": 6.8,
                },
            },
            "files": [
                {
                    "path": "src/main/resources/transforms/transform.dwl",
                    "purpose": "DataWeave topic and header rewrite transform",
                    "content": (
                        "%dw 2.0\n"
                        "output application/json\n"
                        "---\n"
                        "{ headers: { topic: "
                        "'uns/site-a/line-7/compressor-42/telemetry/v1' }, "
                        "payload: payload }"
                    ),
                }
            ],
            "validationNotes": [
                "Assumed Sparkplug group, edge, and node fields map to UNS hierarchy."
            ],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.services.builder_service.httpx.post", mock_litellm_post)

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    def override_get_db() -> Iterator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        input_response = client.post(
            "/api/builder/input-events",
            headers=admin_headers,
            json={
                "sourceName": "Sparkplug edge node",
                "topicName": "sparkplug/plant1/line7/compressor42",
                "inputFormat": "json",
                "headers": {
                    "topic": "spBv1.0/plant1/DDATA/line7/compressor42",
                    "correlationId": "corr-42",
                },
                "payload": {
                    "asset": "compressor-42",
                    "site": "site-a",
                    "line": "line-7",
                    "metrics": {
                        "temperatureC": 74.2,
                        "pressureBar": 6.8,
                    },
                },
            },
        )
        assert input_response.status_code == 200
        input_event = input_response.json()
        assert input_event["headers"]["topic"] == (
            "spBv1.0/plant1/DDATA/line7/compressor42"
        )

        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": input_event["id"],
                "transformLanguage": "dataweave",
            },
        )
        assert session_response.status_code == 200
        builder_session = session_response.json()

        message_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/messages",
            headers=admin_headers,
            json={
                "content": (
                    "Rewrite this Sparkplug message to a UNS topic. Update the topic "
                    "header and publish to the new UNS destination while preserving "
                    "correlation headers."
                ),
                "transformLanguage": "dataweave",
            },
        )
        assert message_response.status_code == 200
        draft = message_response.json()["draft"]
        assert draft["headerMapping"]["topicHeader"] == (
            "uns/site-a/line-7/compressor-42/telemetry/v1"
        )
        assert draft["sampleOutput"]["headers"]["sourceTopic"] == (
            "spBv1.0/plant1/DDATA/line7/compressor42"
        )

        generate_response = client.post(
            f"/api/builder/sessions/{builder_session['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        body = generate_response.json()
        assert body["run"]["canonicalModel"]["topics"] == [
            "uns/site-a/line-7/compressor-42/telemetry/v1"
        ]
        assert len(seen_prompt_payloads) == 1

        archive_response = client.get(f"/api/runs/{body['run']['id']}/workspace.zip")
        assert archive_response.status_code == 200
        with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
            transform_content = archive.read(
                "src/main/resources/transforms/transform.dwl"
            ).decode()
            sample_output = archive.read(
                "src/main/resources/transforms/sample-output.json"
            ).decode()
        assert "uns/site-a/line-7/compressor-42/telemetry/v1" in transform_content
        assert "sourceTopic" in sample_output
    finally:
        app.dependency_overrides.clear()


def test_live_solace_capture_uses_existing_node_script(
    monkeypatch, tmp_path: Path
) -> None:
    script = _capture_script_path()
    assert script.exists()
    assert script.name == "solace_capture_node.js"

    manager = SolaceCaptureManager()
    missing_script = tmp_path / "missing-capture.js"
    monkeypatch.setattr(capture_service, "_capture_script_path", lambda: missing_script)
    state = manager.start(
        None,  # type: ignore[arg-type]
        broker_url="wss://example.test:443",
        vpn="default",
        username="user",
        password="password",
        topic_filter="orders/>",
    )

    assert state.status == "failed"
    assert state.message == "Solace capture script was not found"
