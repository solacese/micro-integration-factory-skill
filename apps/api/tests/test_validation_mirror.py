import importlib.util
from pathlib import Path
import json
import pytest


@pytest.fixture
def worker():
    path = Path(__file__).parents[3] / "infra/validation/worker.py"
    spec = importlib.util.spec_from_file_location("validation_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_pins_base_digests_and_preserves_stage_aliases(worker, tmp_path, monkeypatch):
    original = "FROM golang:1.27.3-alpine AS build\nWORKDIR /src\nFROM scratch\nCOPY --from=build /mi /mi\n"
    source = tmp_path / "Dockerfile"
    source.write_text(original)
    mirror = "123456789012.dkr.ecr.us-east-1.amazonaws.com/factory/images@sha256:" + "a" * 64
    monkeypatch.setenv("VALIDATION_BASE_IMAGES", json.dumps({"golang:1.27.3-alpine": mirror}))
    worker.mirrored_dockerfile(tmp_path)
    assert source.read_text() == original.replace("golang:1.27.3-alpine", mirror)
    assert "FROM scratch" in source.read_text()


def test_unapproved_build_base_is_rejected(worker, tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM unapproved/image:latest\n")
    monkeypatch.setenv(
        "VALIDATION_BASE_IMAGES",
        json.dumps({"golang:1.27.3-alpine": "verified@sha256:" + "a" * 64}),
    )
    with pytest.raises(ValueError, match="Unapproved"):
        worker.mirrored_dockerfile(tmp_path)


def test_mirror_credentials_do_not_change_existing_docker_login(tmp_path, monkeypatch):
    path = Path(__file__).parents[3] / "infra/validation/mirror_images.py"
    spec = importlib.util.spec_from_file_location("mirror_images", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = '{"credsStore":"desktop","auths":{"existing.example":{}}}'
    (tmp_path / "config.json").write_text(original)
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path))
    with module.credential_environment("private.example", "fixture-token-only") as environment:
        directory = Path(environment["DOCKER_CONFIG"])
        assert "fixture-token-only" not in (directory / "config.json").read_text()
        assert environment["MI_FACTORY_ECR_TOKEN"] == "fixture-token-only"
    assert not directory.exists()
    assert (tmp_path / "config.json").read_text() == original
