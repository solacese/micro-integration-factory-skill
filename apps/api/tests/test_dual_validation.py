import base64
import copy
import io
import json
from pathlib import Path
import zipfile

import pytest

from spec2event.services.dual_project_service import create_dual_projects
from spec2event.services.validation_service import ValidationService, report_passes


def sample():
    return json.loads(
        (Path(__file__).parents[1] / "resources/samples/core-java/uppercase.json").read_text()
    )


def contents(artifact):
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(artifact["zipBase64"]))) as archive:
        return {"/".join(Path(n).parts[1:]): archive.read(n) for n in archive.namelist()}


def test_equivalent_contracts_and_identical_shared_yaml_without_mutating_spec():
    spec = sample()
    original = copy.deepcopy(spec)
    project = create_dual_projects(spec)
    java, go = contents(project["java"]), contents(project["go"])
    config = base64.b64decode(project["configuration"]["zipBase64"])
    assert java["config/mi-config.yaml"] == go["config/mi-config.yaml"] == config
    assert java["src/test/resources/core-examples.json"] == go["core-examples.json"]
    assert "replace-me" in config.decode()
    assert spec == original
    assert "transport_amqp.go" in go and "transport_smf.go" not in go
    assert "CGO_ENABLED=0" in go["Dockerfile"].decode()
    assert set(json.loads(go["generation.json"])["verification"].values()) == {"not_run"}


def test_native_smf_profile_selects_sdk_and_cgo_image():
    spec = sample()
    spec["go_transport"] = "smf"
    files = contents(create_dual_projects(spec)["go"])
    assert "transport_smf.go" in files and "transport_amqp.go" not in files
    assert "solace.dev/go/messaging v1.10.1" in files["go.mod"].decode()
    assert "bookworm" in files["Dockerfile"].decode()
    assert json.loads(files["generation.json"])["goTransport"] == "smf"


def passing_report():
    metric = {
        "passed": True,
        "achievedRate": 1010,
        "targetRate": 1000,
        "durationSeconds": 10,
        "sent": 10200,
        "received": 10200,
        "errors": 0,
        "duplicates": 0,
    }
    return {"status": "passed", "runtimes": {"java": dict(metric), "go": dict(metric)}}


@pytest.mark.parametrize(
    "change",
    [
        {"achievedRate": 999.9},
        {"achievedRate": float("nan")},
        {"received": 10199},
        {"errors": 1},
        {"duplicates": 1},
        {"durationSeconds": 9},
        {"sent": 9999},
        {"passed": False},
    ],
)
def test_neither_runtime_can_bypass_the_performance_gate(change):
    report = passing_report()
    assert report_passes(report)
    for language in ["java", "go"]:
        broken = copy.deepcopy(report)
        broken["runtimes"][language].update(change)
        assert not report_passes(broken)
    assert not report_passes({"status": "passed", "runtimes": {"go": report["runtimes"]["go"]}})


def test_validation_receipt_is_bound_to_job_and_expiry(monkeypatch):
    service = ValidationService()
    job = "a" * 32
    token = service._token(job, "b" * 64)
    assert service._verify(job, token)["digest"] == "b" * 64
    with pytest.raises(ValueError):
        service._verify("c" * 32, token)
    with pytest.raises(ValueError):
        service._verify(job, token[:-1] + "z")
    monkeypatch.setattr("spec2event.services.validation_service.time.time", lambda: 10**12)
    with pytest.raises(ValueError):
        service._verify(job, token)


def test_unconfigured_worker_cannot_return_an_unverified_download(monkeypatch):
    monkeypatch.delenv("VALIDATION_BUCKET", raising=False)
    monkeypatch.delenv("VALIDATION_PROJECT", raising=False)
    with pytest.raises(RuntimeError):
        ValidationService().submit({"java": {"zipBase64": "anything"}})


class MemoryS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self, objects):
        self.objects = objects

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(json.dumps(self.objects[Key]).encode())}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        assert ExpiresIn <= 3600
        return "https://private-download.example/" + Params["Key"]


@pytest.mark.parametrize("valid", [True, False])
def test_only_bound_complete_reports_unlock_downloads(monkeypatch, valid):
    project = create_dual_projects(sample())
    service = ValidationService()
    job = "a" * 32
    digest = "b" * 64
    prefix = "jobs/" + job + "/"
    report = passing_report()
    report.update(inputSha256=digest, jobId=job)
    report["downloads"] = {
        lang: {
            "key": prefix + "downloads/" + project[lang]["filename"],
            "filename": project[lang]["filename"],
            "sha256": project[lang]["sha256"],
            "contentType": "application/zip",
        }
        for lang in ["java", "go", "configuration", "tests"]
    }
    if not valid:
        report["runtimes"]["java"]["achievedRate"] = 999
    objects = {
        prefix + "job.json": {"inputSha256": digest, "sources": [], "buildId": "fixture"},
        prefix + "input.json": {"project": project},
        prefix + "report.json": report,
    }
    monkeypatch.setattr(service, "_clients", lambda: (MemoryS3(objects), None))
    result = service.status(job, service._token(job, digest))
    assert result["status"] == ("generated" if valid else "validation_failed")
    if valid:
        assert all(
            result["project"][lang].get("downloadUrl")
            and "zipBase64" not in result["project"][lang]
            for lang in ["java", "go", "configuration", "tests"]
        )
    else:
        assert result["project"] is None
    objects[prefix + "report.json"]["inputSha256"] = "c" * 64
    with pytest.raises(ValueError):
        service.status(job, service._token(job, digest))


@pytest.mark.parametrize(
    "declaration",
    [
        'var ErrInvalidInput = errors.New("bad")',
        "func validTopic(value string)bool{return true}",
        "type Config struct{}",
    ],
)
def test_generated_core_cannot_redeclare_provided_go_symbols(declaration):
    spec = sample()
    spec["core_go"] += "\n" + declaration + "\n"
    with pytest.raises(ValueError, match="Go runtime already declares"):
        create_dual_projects(spec)


def test_fourth_archive_contains_generated_binary_examples_and_sdkperf_tools():
    project = create_dual_projects(sample())
    files = contents(project["tests"])
    assert files["config/mi-config.yaml"] == base64.b64decode(project["configuration"]["zipBase64"])
    assert files["fixtures/01-valid.input.bin"] == b"hello"
    assert files["fixtures/01-valid.expected.bin"] == b"HELLO"
    assert files["fixtures/02-invalid.input.bin"] == b""
    assert "performance/main.go" in files and "performance/broker.go" in files
    assert "generated-tests/go/core_test.go" in files
    assert any(
        name.startswith("generated-tests/java/") and name.endswith("CoreContractTest.java")
        for name in files
    )
    manifest = json.loads(files["test-manifest.json"])
    assert manifest["sdkPerf"]["binaryIncluded"] is False
    assert manifest["sdkPerf"]["execution"] == "not_run"
    assert "sdkperf-publish" in manifest["commands"]
    assert not any(name.endswith(".jar") for name in files)
    assert project["tests"]["sha256"] == create_dual_projects(sample())["tests"]["sha256"]


def test_missing_test_download_is_not_accepted_for_new_generations(monkeypatch):
    project = create_dual_projects(sample())
    service = ValidationService()
    job = "a" * 32
    digest = "b" * 64
    prefix = "jobs/" + job + "/"
    report = passing_report()
    report.update(inputSha256=digest, jobId=job)
    report["downloads"] = {
        lang: {
            "key": prefix + "downloads/" + project[lang]["filename"],
            "filename": project[lang]["filename"],
            "sha256": project[lang]["sha256"],
            "contentType": "application/zip",
        }
        for lang in ["java", "go", "configuration"]
    }
    objects = {
        prefix + "job.json": {"inputSha256": digest, "sources": [], "buildId": "fixture"},
        prefix + "input.json": {"project": project},
        prefix + "report.json": report,
    }
    monkeypatch.setattr(service, "_clients", lambda: (MemoryS3(objects), None))
    with pytest.raises(RuntimeError, match="missing"):
        service.status(job, service._token(job, digest))
    # Previously generated jobs remain downloadable; only new jobs require four artifacts.
    del objects[prefix + "input.json"]["project"]["tests"]
    assert service.status(job, service._token(job, digest))["status"] == "generated"


def test_test_kit_preserves_binary_schema_payloads():
    spec = sample()
    spec["core_java"] = (
        "package com.solace.mi; import java.util.Map; public class Core { public byte[] process(byte[] payload, Map<String,Object> headers) { return payload.clone(); } }"
    )
    spec["core_go"] = (
        "package main\n// Return the original binary event without text decoding or transcoding.\nfunc Process(payload []byte, headers map[string]any) ([]byte,error) { return append([]byte{},payload...),nil }"
    )
    payload = b"\x00\xff\x80\x01"
    spec["examples"] = [
        {
            "input_base64": base64.b64encode(payload).decode(),
            "output_base64": base64.b64encode(payload).decode(),
        }
    ]
    files = contents(create_dual_projects(spec)["tests"])
    assert files["fixtures/01-valid.input.bin"] == payload
    assert files["fixtures/01-valid.expected.bin"] == payload


def test_test_kit_receives_both_qualified_reports_and_raw_latency_files():
    import importlib.util

    path = Path(__file__).parents[3] / "infra/validation/worker.py"
    definition = importlib.util.spec_from_file_location("kit_worker", path)
    worker = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(worker)
    project = create_dual_projects(sample())
    report = passing_report()
    measured = {"java": {"csv": b"id,latency_ms\n1,2\n"}, "go": {"csv": b"id,latency_ms\n1,1\n"}}
    data = worker.enrich_test_archive(
        base64.b64decode(project["tests"]["zipBase64"]), report, measured
    )
    files = contents({"zipBase64": base64.b64encode(data).decode()})
    assert json.loads(files["reports/validation.json"]) == report
    assert files["reports/java.csv"] == measured["java"]["csv"]
    assert files["reports/go.csv"] == measured["go"]["csv"]
    manifest = json.loads(files["test-manifest.json"])
    assert manifest["verification"] == "passed"
    assert manifest["sdkPerf"]["execution"] == "not_run"
