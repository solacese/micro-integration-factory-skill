from __future__ import annotations

import json
from pathlib import Path

from spec2event import one_shot_hybrid
from spec2event.config import get_settings


def _source_bundle() -> one_shot_hybrid.HybridSourceBundle:
    return one_shot_hybrid.HybridSourceBundle(
        raw_spec="openapi: 3.0.3\ninfo:\n  title: Stripe Demo\n  version: 1.0.0\npaths: {}\n",
        openapi_summary={
            "title": "Stripe Demo",
            "version": "1.0.0",
            "serviceName": "stripe-demo",
            "operationCount": 2,
        },
        openapi_model={
            "serviceName": "stripe-demo",
            "topics": ["commerce/stripe/payment_intent/succeeded/v1"],
        },
        database_discovery={
            "databaseKind": "postgres",
            "selectedTableQualifiedName": "public.products",
            "rowCount": 42,
        },
        database_model={
            "serviceName": "postgres-products",
            "topics": ["commerce/postgres-products/product/observed/v1"],
        },
    )


def test_parse_args_defaults_to_full() -> None:
    args = one_shot_hybrid.parse_args([])

    assert args.mode == "full"


def test_run_validate_mode_generates_and_validates_without_full_flow(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "generated-runs"))
    get_settings.cache_clear()

    discovery_calls: list[str] = []
    generate_calls: list[tuple[str, str]] = []
    validation_calls: list[str] = []

    def fake_discover_sources() -> one_shot_hybrid.HybridSourceBundle:
        discovery_calls.append("discover")
        return _source_bundle()

    def fake_openapi_generate(
        run_id: str,
        canonical_model: dict,
        openapi_summary: dict,
        raw_spec: str,
    ) -> Path:
        del canonical_model, openapi_summary, raw_spec
        workspace = tmp_path / "generated-runs" / run_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        generate_calls.append(("openapi", run_id))
        return workspace

    def fake_database_generate(
        run_id: str,
        canonical_model: dict,
        discovery_summary: dict,
    ) -> Path:
        del canonical_model, discovery_summary
        workspace = tmp_path / "generated-runs" / run_id / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        generate_calls.append(("postgres", run_id))
        return workspace

    def fake_validate_workspace(workspace: Path) -> str:
        validation_calls.append(str(workspace))
        return f"validated {workspace.parent.name}"

    def unexpected(*_args, **_kwargs):
        raise AssertionError("full-flow dependency should not be used in validate mode")

    monkeypatch.setattr(one_shot_hybrid, "_load_env_file", lambda path: None)
    monkeypatch.setattr(one_shot_hybrid, "_discover_sources", fake_discover_sources)
    monkeypatch.setattr(one_shot_hybrid, "_ensure_target_supported", unexpected)
    monkeypatch.setattr(one_shot_hybrid, "_ensure_node_bridge_dependencies", unexpected)
    monkeypatch.setattr(one_shot_hybrid.generator_service, "generate", fake_openapi_generate)
    monkeypatch.setattr(
        one_shot_hybrid.database_generator_service,
        "generate",
        fake_database_generate,
    )
    monkeypatch.setattr(one_shot_hybrid, "_validate_workspace", fake_validate_workspace)
    monkeypatch.setattr(one_shot_hybrid, "AwsService", unexpected)
    monkeypatch.setattr(one_shot_hybrid, "EcrDockerBuildEngine", unexpected)
    monkeypatch.setattr(one_shot_hybrid, "EphemeralEc2DeploymentAdapter", unexpected)
    monkeypatch.setattr(one_shot_hybrid, "SolaceEventPortalAdapter", unexpected)

    summary = one_shot_hybrid.run(mode="validate")

    assert discovery_calls == ["discover"]
    assert len(generate_calls) == 2
    assert {name for name, _ in generate_calls} == {"openapi", "postgres"}
    assert len(validation_calls) == 2

    assert summary["mode"] == "validate"
    assert summary["openapi"]["validation_status"] == "completed"
    assert summary["postgres"]["validation_status"] == "completed"
    assert summary["openapi"]["build_status"] == "skipped"
    assert summary["postgres"]["build_status"] == "skipped"
    assert summary["openapi"]["deploy_status"] == "skipped"
    assert summary["postgres"]["deploy_status"] == "skipped"
    assert summary["openapi"]["portal_status"] == "skipped"
    assert summary["postgres"]["portal_status"] == "skipped"
    assert summary["openapi"]["verification"] is None
    assert summary["postgres"]["verification"] is None

    summary_files = list((tmp_path / "generated-runs").rglob("summary.json"))
    assert len(summary_files) == 1
    persisted_summary = json.loads(summary_files[0].read_text(encoding="utf-8"))
    assert persisted_summary["mode"] == "validate"
    assert persisted_summary["openapi"]["validation_status"] == "completed"
    assert persisted_summary["postgres"]["validation_status"] == "completed"
    assert persisted_summary["openapi"]["build_status"] == "skipped"
    assert persisted_summary["postgres"]["deploy_status"] == "skipped"

    summary_md = summary_files[0].with_name("summary.md").read_text(encoding="utf-8")
    assert "Both runtimes were generated and validated locally." in summary_md
    assert (
        "Build, deployment, Solace verification, and Event Portal sync were skipped."
        in summary_md
    )
