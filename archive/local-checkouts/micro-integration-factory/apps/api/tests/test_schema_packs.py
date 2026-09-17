from __future__ import annotations

import json as json_module
from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from spec2event.config import get_settings
from spec2event.db import Base, get_db
from spec2event.main import app

HL7_SIU_S12_SCHEMA = """
form: HL7
version: '2.5.1'
structures:
- id: 'SIU_S12'
  name: 'SIU_S12'
  data:
  - { idRef: 'MSH', position: '01', usage: R }
  - { idRef: 'SCH', position: '02', usage: R }
  - groupId: 'PATIENT'
    count: '>1'
    usage: O
    items:
    - { idRef: 'PID', position: '06', usage: O }
    - { idRef: 'PV1', position: '08', usage: O }
  - groupId: 'RESOURCES'
    count: '>1'
    usage: O
    items:
    - { idRef: 'RGS', position: '14', usage: O }
    - groupId: 'SERVICE'
      count: '>1'
      usage: O
      items:
      - { idRef: 'AIS', position: '16', usage: O }
segments:
- id: 'MSH'
  name: 'Message Header'
  varTag: 'MSH'
  values:
  - { idRef: 'ST', name: 'Sending Application', usage: R }
  - { idRef: 'ST', name: 'Sending Facility', usage: O }
- id: 'SCH'
  name: 'Schedule Activity Information'
  varTag: 'SCH'
  values:
  - { idRef: 'EI', name: 'Placer Appointment ID', usage: R }
  - { idRef: 'TS', name: 'Appointment Date/Time', usage: R }
- id: 'PID'
  name: 'Patient Identification'
  varTag: 'PID'
  values:
  - { idRef: 'CX', name: 'Patient Identifier List', usage: R, count: '>1' }
  - { idRef: 'XPN', name: 'Patient Name', usage: O }
composites:
- id: 'CX'
  name: 'Extended Composite ID'
  values:
  - { idRef: 'ST', name: 'ID Number', usage: R }
"""

GENERIC_EDI_SCHEMA = """
form: EDI
version: D96A
structures:
- id: DESADV
  name: Dispatch Advice
  data:
  - { idRef: UNH, position: '01', usage: R }
  - { idRef: BGM, position: '02', usage: R }
segments:
- id: UNH
  name: Message Header
  values:
  - { idRef: '0062', name: Message reference number, usage: R }
- id: BGM
  name: Beginning of Message
  values:
  - { idRef: '1004', name: Document number, usage: R }
"""


def _client(monkeypatch, tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "schema-pack-runs"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
    monkeypatch.setenv("ENABLE_LOCAL_WORKER", "false")
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
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
    return TestClient(app), {"X-Demo-Admin-Password": "test-password"}


def test_schema_pack_crud_and_parsing(monkeypatch, tmp_path: Path) -> None:
    client, admin_headers = _client(monkeypatch, tmp_path)
    try:
        response = client.post(
            "/api/schema-packs",
            headers=admin_headers,
            json={
                "name": "HL7 SIU_S12",
                "schemaFormat": "hl7",
                "version": "2.5.1",
                "messageType": "SIU_S12",
                "industry": "Healthcare",
                "rawContent": HL7_SIU_S12_SCHEMA,
            },
        )
        assert response.status_code == 200
        pack = response.json()
        assert pack["messageType"] == "SIU_S12"
        assert pack["summary"]["exampleMessageType"] == "SIU_S12"
        assert pack["summary"]["counts"]["structures"] == 1
        assert pack["summary"]["counts"]["segments"] == 3
        assert pack["summary"]["counts"]["composites"] == 1
        assert pack["summary"]["counts"]["fields"] == 7
        assert any("PID.CX" in hint for hint in pack["summary"]["repeatingHints"])

        edi_response = client.post(
            "/api/schema-packs",
            headers=admin_headers,
            json={
                "name": "ODETTE DESADV",
                "schemaFormat": "generic_edi",
                "version": "D96A",
                "messageType": "DESADV",
                "industry": "Automotive",
                "rawContent": GENERIC_EDI_SCHEMA,
            },
        )
        assert edi_response.status_code == 200
        assert edi_response.json()["summary"]["exampleMessageType"] == "DESADV"

        list_response = client.get("/api/schema-packs")
        assert list_response.status_code == 200
        assert len(list_response.json()) == 2

        detail_response = client.get(f"/api/schema-packs/{pack['id']}")
        assert detail_response.status_code == 200
        assert "SIU_S12" in detail_response.json()["rawContent"]

        delete_response = client.delete(
            f"/api/schema-packs/{pack['id']}",
            headers=admin_headers,
        )
        assert delete_response.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_builder_uses_schema_pack_and_settings_litellm(monkeypatch, tmp_path: Path) -> None:
    client, admin_headers = _client(monkeypatch, tmp_path)
    seen_prompts: list[dict] = []

    def mock_settings_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, json, timeout

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": "ok"}}]}

        return MockResponse()

    def mock_builder_litellm_post(url, headers, json: dict, timeout):  # noqa: ANN001
        del url, headers, timeout
        prompt_payload = json_module.loads(json["messages"][1]["content"])
        seen_prompts.append(prompt_payload)
        assert prompt_payload["schemaPack"]["exampleMessageType"] == "SIU_S12"
        assert prompt_payload["schemaPack"]["segments"][0]["id"] == "MSH"
        assert prompt_payload["inputMessage"]["inputFormat"] == "hl7"
        draft = {
            "transformLanguage": "dataweave",
            "intentSummary": "Map HL7 SIU_S12 appointments into canonical events.",
            "assistantMessage": (
                "Wrote transform.dwl for SIU_S12 appointments and publish "
                "to healthcare/appointment/scheduled/v1."
            ),
            "qualifyingQuestions": [],
            "topicMapping": {
                "inputTopic": "systems/hospital/hl7/siu-s12/v1",
                "outputTopic": "healthcare/appointment/scheduled/v1",
            },
            "sampleOutput": {
                "eventType": "AppointmentScheduled",
                "appointmentId": "A100",
                "patientId": "P123",
                "startTime": "2026-06-01T09:30:00",
            },
            "files": [
                {
                    "path": "src/main/resources/transforms/transform.dwl",
                    "purpose": "HL7 SIU_S12 DataWeave transform",
                    "content": (
                        "%dw 2.0\n"
                        "output application/json\n"
                        "---\n"
                        "{ eventType: 'AppointmentScheduled', "
                        "appointmentId: 'A100', patientId: 'P123' }"
                    ),
                }
            ],
            "validationNotes": [
                "Mapped MSH as message envelope metadata.",
                "Mapped SCH placer appointment ID to appointmentId.",
                "Mapped PID patient identifier list to patientId.",
            ],
        }

        class MockResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": json_module.dumps(draft)}}]}

        return MockResponse()

    monkeypatch.setattr("spec2event.api.routes.httpx.post", mock_settings_litellm_post)

    try:
        missing_test = client.post(
            "/api/settings/litellm/test",
            headers=admin_headers,
            json={},
        )
        assert missing_test.status_code == 200
        assert missing_test.json()["ok"] is False

        settings_response = client.put(
            "/api/settings",
            headers=admin_headers,
            json={
                "litellmBaseUrl": "https://litellm.test",
                "litellmApiKey": "stored-test-key",
                "litellmModel": "bedrock-claude-4-5-sonnet",
            },
        )
        assert settings_response.status_code == 200
        assert settings_response.json()["hasLiteLlmConfig"] is True
        assert settings_response.json()["litellmBaseUrl"] == "https://litellm.test"
        assert "litellmApiKey" not in settings_response.json()

        connection_test = client.post(
            "/api/settings/litellm/test",
            headers=admin_headers,
            json={},
        )
        assert connection_test.status_code == 200
        assert connection_test.json()["ok"] is True

        schema_response = client.post(
            "/api/schema-packs",
            headers=admin_headers,
            json={
                "name": "HL7 SIU_S12 appointment",
                "schemaFormat": "hl7",
                "version": "2.5.1",
                "messageType": "SIU_S12",
                "industry": "Healthcare",
                "rawContent": HL7_SIU_S12_SCHEMA,
            },
        )
        assert schema_response.status_code == 200
        schema_pack_id = schema_response.json()["id"]

        input_response = client.post(
            "/api/builder/input-events",
            headers=admin_headers,
            json={
                "sourceName": "Hospital HL7 feed",
                "topicName": "systems/hospital/hl7/siu-s12/v1",
                "inputFormat": "hl7",
                "payload": (
                    "MSH|^~\\&|HIS|HOSP|RIS|HOSP|202606010900||SIU^S12|1|P|2.5.1\\r"
                    "SCH|A100||||||||202606010930\\r"
                    "PID|||P123||DOE^JANE"
                ),
            },
        )
        assert input_response.status_code == 200

        session_response = client.post(
            "/api/builder/sessions",
            headers=admin_headers,
            json={
                "capturedEventId": input_response.json()["id"],
                "transformLanguage": "dataweave",
            },
        )
        assert session_response.status_code == 200

        monkeypatch.setattr(
            "spec2event.services.builder_service.httpx.post",
            mock_builder_litellm_post,
        )
        message_response = client.post(
            f"/api/builder/sessions/{session_response.json()['id']}/messages",
            headers=admin_headers,
            json={
                "content": (
                    "Use the SIU_S12 schema pack to publish a canonical appointment "
                    "scheduled event for OpenEMR/API consumers."
                ),
                "transformLanguage": "dataweave",
                "schemaPackId": schema_pack_id,
            },
        )
        assert message_response.status_code == 200
        draft = message_response.json()["draft"]
        assert draft["schemaPackId"] == schema_pack_id
        assert draft["schemaPack"]["exampleMessageType"] == "SIU_S12"
        assert draft["topicMapping"]["outputTopic"] == "healthcare/appointment/scheduled/v1"
        assert "PID" in " ".join(draft["validationNotes"])

        generate_response = client.post(
            f"/api/builder/sessions/{session_response.json()['id']}/generate",
            headers=admin_headers,
        )
        assert generate_response.status_code == 200
        assert generate_response.json()["run"]["canonicalModel"]["topics"] == [
            "healthcare/appointment/scheduled/v1"
        ]
        assert len(seen_prompts) == 1
    finally:
        app.dependency_overrides.clear()


def test_deploy_script_uses_refreshable_aws_credentials_not_litellm_key() -> None:
    script = Path(__file__).resolve().parents[3] / "infra" / "scripts" / "deploy.sh"
    content = script.read_text(encoding="utf-8")
    assert "AWS_PROFILE" in content
    assert "aws sso login" in content
    assert "AWS_ROLE_ARN" in content
    assert "Missing required .env values" not in content
    assert "LITELLM_API_KEY" not in content
