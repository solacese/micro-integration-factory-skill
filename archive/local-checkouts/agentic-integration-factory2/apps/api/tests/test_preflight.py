from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx


def _load_preflight_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "preflight.py"
    spec = importlib.util.spec_from_file_location("repo_preflight", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_database_url_uses_individual_fields(monkeypatch) -> None:
    preflight = _load_preflight_module()
    monkeypatch.delenv("SOURCE_DATABASE_URL", raising=False)
    monkeypatch.setenv("SOURCE_DATABASE_HOST", "db.example")
    monkeypatch.setenv("SOURCE_DATABASE_PORT", "5432")
    monkeypatch.setenv("SOURCE_DATABASE_NAME", "catalog")
    monkeypatch.setenv("SOURCE_DATABASE_USERNAME", "reader")
    monkeypatch.setenv("SOURCE_DATABASE_PASSWORD", "secret")
    monkeypatch.setenv("SOURCE_DATABASE_SSLMODE", "require")

    value = preflight._database_url()

    assert value == "postgresql://reader:secret@db.example:5432/catalog?sslmode=require"


def test_check_ec2_prereqs_reports_missing_network_values(monkeypatch) -> None:
    preflight = _load_preflight_module()
    monkeypatch.setenv("DEPLOYMENT_TARGET", "ec2")
    monkeypatch.delenv("DEPLOY_EC2_HOST", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_SUBNET_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_VPC_ID", raising=False)
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)

    result = preflight.check_ec2_prereqs()

    assert result["ok"] is False
    assert result["mode"] == "ephemeral_ec2"
    assert result["missing"] == [
        "CONTROL_PLANE_SUBNET_ID",
        "CONTROL_PLANE_VPC_ID",
        "PUBLIC_BASE_URL",
    ]


def test_check_event_portal_surfaces_tls_errors(monkeypatch) -> None:
    preflight = _load_preflight_module()
    monkeypatch.setenv("EVENT_PORTAL_BASE_URL", "https://solace-sso.solace.cloud/ep/designer")
    monkeypatch.setenv("EVENT_PORTAL_TOKEN", "token")

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, *_args, **_kwargs):
            raise httpx.ConnectError(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
            )

    monkeypatch.setattr(preflight.httpx, "Client", lambda **_kwargs: FakeClient())

    result = preflight.check_event_portal()

    assert result["ok"] is False
    assert result["error"] == "TLSVerificationError"
    assert "trust store" in result["hint"]


def test_check_ecr_reports_repository_uri(monkeypatch) -> None:
    preflight = _load_preflight_module()
    monkeypatch.setenv("ECR_REPOSITORY_NAME", "factory-images")

    class FakeEcr:
        def describe_repositories(self, repositoryNames):
            assert repositoryNames == ["factory-images"]
            return {
                "repositories": [
                    {
                        "repositoryName": "factory-images",
                        "repositoryUri": "123456789012.dkr.ecr.ca-central-1.amazonaws.com/factory-images",
                    }
                ]
            }

    class FakeSession:
        def client(self, service_name):
            assert service_name == "ecr"
            return FakeEcr()

    monkeypatch.setattr(preflight.boto3, "Session", lambda **_kwargs: FakeSession())

    result = preflight.check_ecr()

    assert result["ok"] is True
    assert result["repository"] == "factory-images"
    assert result["repositoryUri"].endswith("/factory-images")
