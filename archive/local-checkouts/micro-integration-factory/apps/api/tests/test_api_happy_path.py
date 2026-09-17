from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from spec2event.api.routes import _dump_run_payload
from spec2event.config import get_settings
from spec2event.db import Base, get_db
from spec2event.main import app
from spec2event.services.generator_service import generator_service
from spec2event.services.openapi_service import (
    canonicalize_openapi,
    load_openapi_document,
    summarize_openapi,
)
from spec2event.services.run_service import (
    create_run,
    create_upload,
    get_run,
    log_step,
    snapshot_workspace,
    update_run,
)

API_ROOT = Path(__file__).resolve().parents[1]
STRIPE_SPEC = API_ROOT / "resources" / "samples" / "openapi" / "stripe-webhook-demo.yaml"


def test_upload_and_generate_happy_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
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

    def inline_generation(run_id: str, auto_build: bool = False, auto_deploy: bool = False) -> None:
        del auto_build, auto_deploy
        with testing_session_local() as db:
            run = get_run(db, run_id)
            upload = run.upload
            document = load_openapi_document(upload.raw_content)
            summary = summarize_openapi(document)
            canonical_model = canonicalize_openapi(document)

            update_run(db, run, status="running", last_message="Generating workspace")
            log_step(db, run, "uploaded", "completed", "OpenAPI upload accepted")
            log_step(db, run, "parsed", "completed", "Parsed OpenAPI document")
            log_step(db, run, "canonicalized", "completed", "Derived canonical event model")

            workspace = generator_service.generate(
                run.id,
                canonical_model,
                summary,
                upload.raw_content,
            )
            update_run(
                db,
                run,
                status="completed",
                service_name=canonical_model["serviceName"],
                workspace_path=str(workspace),
                canonical_model_json=canonical_model,
                last_message="Generation complete",
            )
            snapshot_workspace(db, run, workspace)
            log_step(db, run, "generated", "completed", "Generated MDK workspace")
            log_step(db, run, "ready", "completed", "Run is ready for build, deploy, and test")
            db.commit()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("spec2event.api.routes.enqueue_generation", inline_generation)
    client = TestClient(app)
    admin_headers = {"X-Demo-Admin-Password": "test-password"}

    try:
        with STRIPE_SPEC.open("rb") as handle:
            upload_response = client.post(
                "/api/uploads",
                files={"file": ("stripe-webhook-demo.yaml", handle, "application/yaml")},
                headers=admin_headers,
            )

        assert upload_response.status_code == 200
        upload_body = upload_response.json()
        assert upload_body["serviceName"] == "stripe-payments-gateway"

        create_run_response = client.post(
            "/api/runs",
            json={
                "uploadId": upload_body["uploadId"],
                "deploymentTarget": "local_docker",
                "autoBuild": False,
                "autoDeploy": False,
            },
            headers=admin_headers,
        )
        assert create_run_response.status_code == 200
        run_id = create_run_response.json()["id"]

        run_response = client.get(f"/api/runs/{run_id}")
        assert run_response.status_code == 200
        run_body = run_response.json()
        assert run_body["status"] == "completed"
        assert "payments/stripe/payment_intent/succeeded/v1" in run_body["canonicalModel"]["topics"]
        assert run_body["activeDeployment"] is None
        assert run_body["canonicalModel"]["testFixtures"]

        artifact_response = client.get(f"/api/runs/{run_id}/artifacts")
        assert artifact_response.status_code == 200
        artifact_paths = {artifact["path"] for artifact in artifact_response.json()}
        assert "pom.xml" in artifact_paths
        assert "src/main/resources/application.yml" in artifact_paths
        assert "ui/ui-metadata.json" in artifact_paths
    finally:
        app.dependency_overrides.clear()


def test_stream_payload_serializer_uses_camel_case(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "test-password")
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

    try:
        raw_spec = STRIPE_SPEC.read_text(encoding="utf-8")
        summary = summarize_openapi(load_openapi_document(raw_spec))

        with testing_session_local() as db:
            upload = create_upload(
                db,
                "stripe-webhook-demo.yaml",
                "application/yaml",
                raw_spec,
                summary,
            )
            run = create_run(db, upload, "local_docker")
            log_step(db, run, "uploaded", "completed", "OpenAPI upload accepted")
            db.commit()
            payload = json.loads(_dump_run_payload(run))

        assert payload["deploymentTarget"] == "local_docker"
        assert payload["lastMessage"] == "OpenAPI upload accepted"
        assert payload["steps"][0]["stepName"] == "uploaded"
    finally:
        app.dependency_overrides.clear()
