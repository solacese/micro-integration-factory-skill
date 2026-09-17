from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from spec2event import db as db_module
from spec2event.adapters.ai.base import AiRefinementResult, ArtifactPatch
from spec2event.config import get_settings
from spec2event.db import Base
from spec2event.services import pipeline as pipeline_module
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
    latest_artifacts,
    snapshot_workspace,
    update_run,
)

API_ROOT = Path(__file__).resolve().parents[1]
STRIPE_SPEC = API_ROOT / "resources" / "samples" / "openapi" / "stripe-webhook-demo.yaml"


def test_generation_pipeline_persists_failure_progress(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(db_module, "SessionLocal", testing_session_local)

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
        db.commit()
        run_id = run.id

    def explode(*_args, **_kwargs):
        raise RuntimeError("generation exploded")

    monkeypatch.setattr(pipeline_module.generator_service, "generate", explode)

    pipeline_module.generation_pipeline(run_id)

    with testing_session_local() as db:
        run = get_run(db, run_id)
        assert run.status == "failed"
        assert run.last_message == "generation exploded"

        step_states = [(step.step_name, step.status, step.message) for step in run.step_logs]
        assert ("uploaded", "completed", "Source upload accepted (openapi)") in step_states
        assert any(step[0] == "parsed" and step[1] == "completed" for step in step_states)
        assert any(step[0] == "canonicalized" and step[1] == "completed" for step in step_states)
        assert ("generated", "failed", "generation exploded") in step_states


def test_ai_refinement_reverts_invalid_patches(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(db_module, "SessionLocal", testing_session_local)

    raw_spec = STRIPE_SPEC.read_text(encoding="utf-8")
    document = load_openapi_document(raw_spec)
    summary = summarize_openapi(document)
    canonical_model = canonicalize_openapi(document)

    with testing_session_local() as db:
        upload = create_upload(
            db,
            "stripe-webhook-demo.yaml",
            "application/yaml",
            raw_spec,
            summary,
        )
        run = create_run(db, upload, "local_docker")
        workspace = generator_service.generate(run.id, canonical_model, summary, raw_spec)
        update_run(db, run, workspace_path=str(workspace), canonical_model_json=canonical_model)
        snapshot_workspace(db, run, workspace)
        db.commit()
        run_id = run.id
        original_content = (
            workspace
            / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java"
        ).read_text(encoding="utf-8")

    class BrokenAiProvider:
        def __init__(self, *, base_url: str | None, api_key: str | None, model: str | None) -> None:
            del base_url, api_key, model

        def refine(self, canonical_model: dict, artifacts: dict[str, str]) -> AiRefinementResult:
            del canonical_model, artifacts
            return AiRefinementResult(
                applied=True,
                status="completed",
                message="Applied invalid patch",
                patches=[
                    ArtifactPatch(
                        path="src/main/java/com/spec2event/generated/service/CanonicalEventService.java",
                        content=(
                            "package com.spec2event.generated.service;\n"
                            "public class CanonicalEventService {}\n"
                        ),
                    )
                ],
            )

    class FailedCompileResult:
        returncode = 1
        stdout = ""
        stderr = "cannot find symbol planForOperation"

    monkeypatch.setattr(pipeline_module, "LiteLLMRefinementProvider", BrokenAiProvider)
    monkeypatch.setattr(
        pipeline_module,
        "run_command",
        lambda *args, **kwargs: FailedCompileResult(),
    )

    with testing_session_local() as db:
        result = pipeline_module._run_ai_refinement(db, run_id, canonical_model)
        db.commit()

    assert result["status"] == "completed"
    assert "generated project was kept unchanged" in result["message"]

    with testing_session_local() as db:
        run = get_run(db, run_id)
        latest = {
            artifact.path: artifact.content
            for artifact in latest_artifacts(db, run.id)
        }
        restored_content = latest[
            "src/main/java/com/spec2event/generated/service/CanonicalEventService.java"
        ]
        assert restored_content == original_content
        workspace_file = (
            Path(run.workspace_path)
            / "src/main/java/com/spec2event/generated/service/CanonicalEventService.java"
        )
        assert workspace_file.read_text(encoding="utf-8") == original_content
