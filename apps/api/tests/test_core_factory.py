from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import httpx
import pytest

from spec2event.adapters.ai.sap_ai_core import SapAiCoreProvider
from spec2event.services import advisor_service, research_service, service_confirmation
from spec2event.services.core_project_service import create_core_project

CORE = """package com.solace.mi;
import java.util.Map;
import java.nio.charset.StandardCharsets;
public final class Core {
 public byte[] process(byte[] payload, Map<String,Object> headers) {
  String value=new String(payload,StandardCharsets.UTF_8);
  if(value.isBlank()) throw new IllegalArgumentException("Empty input");
  return value.toUpperCase(java.util.Locale.ROOT).getBytes(StandardCharsets.UTF_8);
 }
}
"""


def spec():
    return {
        "name": "upper-case",
        "description": "Uppercase UTF-8 text",
        "core_java": CORE,
        "examples": [{"input": "hello", "output": "HELLO"}, {"input": "", "expected_error": True}],
    }


def generate_after_confirmation(provider, request):
    plan = {"services": [{"name": "Java message processor", "supported": True}], "sources": []}
    token = service_confirmation.seal(plan, request, "")
    return advisor_service.AdvisorService(provider).respond(
        [
            {"role": "user", "content": request},
            {"role": "assistant", "content": "Is this the right service?"},
            {"role": "user", "content": "Yes, generate MI v1"},
        ],
        confirmation_token=token,
    )


def test_download_is_reproducible_complete_and_honest_about_verification():
    first = create_core_project(spec())
    second = create_core_project(spec())
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(first["zipBase64"]))) as archive:
        files = archive.namelist()
        assert all(
            name.startswith("upper-case-mi-v1/") and ".." not in Path(name).parts for name in files
        )
        assert "upper-case-mi-v1/scripts/install.sh" in files
        assert "upper-case-mi-v1/scripts/smoke.sh" in files
        assert "upper-case-mi-v1/.env.example" in files
        assert not any(name.endswith("/.env") for name in files)
        report = json.loads(archive.read("upper-case-mi-v1/generation.json"))
        assert set(report["verification"].values()) == {"not_run"}
        assert report["editableCore"].endswith("/Core.java")
        fixtures = json.loads(
            archive.read("upper-case-mi-v1/src/test/resources/core-examples.json")
        )
        assert base64.b64decode(fixtures[0]["input_base64"]) == b"hello"
        assert base64.b64decode(fixtures[0]["output_base64"]) == b"HELLO"
        assert archive.getinfo("upper-case-mi-v1/scripts/install.sh").external_attr >> 16 & 0o111


@pytest.mark.parametrize(
    "change",
    [
        {"core_java": "// implement later"},
        {"examples": []},
        {"examples": [{"input": "bad", "expected_error": True}]},
        {"dependencies": ["unverified-library"]},
        {"required_env": ["password=value"]},
    ],
)
def test_incomplete_or_invalid_projects_are_not_downloadable(change):
    candidate = spec()
    candidate.update(change)
    with pytest.raises(ValueError):
        create_core_project(candidate)


def test_metadata_cannot_inject_maven_xml_or_archive_paths():
    candidate = spec()
    candidate.update(name="../../escape", description="</description><evil/>")
    result = create_core_project(candidate)
    assert result["filename"] == "escape-mi-v1.zip"
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zipBase64"]))) as archive:
        from xml.etree import ElementTree

        xml = ElementTree.fromstring(archive.read("escape-mi-v1/pom.xml"))
        assert not list(xml.iter("evil"))


def test_research_rejects_private_urls_and_redirects(monkeypatch):
    for url in [
        "http://docs.solace.com/a",
        "https://127.0.0.1/a",
        "https://docs.solace.com@127.0.0.1/",
        "https://docs.solace.com:8443/a",
        "https://raw.githubusercontent.com/untrusted/repo/main/a",
    ]:
        assert not research_service.allowed_url(url)
    client_class = httpx.Client
    calls = []

    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(
        research_service.httpx,
        "Client",
        lambda **kw: client_class(transport=httpx.MockTransport(respond), **kw),
    )
    result = research_service.fetch_reference("https://docs.solace.com/test-redirect")
    assert result["status"] == "unavailable"
    assert calls == ["https://docs.solace.com/test-redirect"]


def test_research_records_fetched_bytes_and_provenance(monkeypatch):
    client_class = httpx.Client
    raw = b"<html><script>ignore</script><main>Official content</main></html>"
    monkeypatch.setattr(
        research_service.httpx,
        "Client",
        lambda **kw: client_class(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, content=raw, headers={"content-type": "text/html"})
            ),
            **kw,
        ),
    )
    result = research_service.fetch_reference("https://docs.solace.com/test-provenance")
    assert result["status"] == "fetched" and result["fetchedAt"]
    assert result["excerpt"] == "Official content"
    import hashlib

    assert result["sha256"] == hashlib.sha256(raw).hexdigest()


def test_soft_404_documentation_is_not_verified_evidence(monkeypatch):
    client_class = httpx.Client

    def respond(request):
        if request.url.path != "/Not-Found.htm":
            return httpx.Response(302, headers={"location": "/Not-Found.htm"})
        return httpx.Response(
            200, text="Sorry, we sent you the wrong way", headers={"content-type": "text/html"}
        )

    monkeypatch.setattr(
        research_service.httpx,
        "Client",
        lambda **kw: client_class(transport=httpx.MockTransport(respond), **kw),
    )
    assert (
        research_service.fetch_reference("https://docs.solace.com/removed-page")["status"]
        == "unavailable"
    )


def test_search_does_not_send_user_payloads_or_credentials_to_search_engine(monkeypatch):
    urls = []

    def search(url, **kwargs):
        urls.append(url)
        return httpx.Response(200, text="<rss><channel/></rss>")

    monkeypatch.setattr(research_service.httpx, "get", search)
    monkeypatch.setattr(
        research_service,
        "fetch_reference",
        lambda url, title: {"url": url, "status": "unavailable"},
    )
    research_service.research(
        "Parse JSON for CustomerPrivateName using password=PrivateCredential123"
    )
    assert len(urls) == 1
    assert "JSON" in urls[0]
    assert "CustomerPrivateName" not in urls[0] and "PrivateCredential123" not in urls[0]


def test_ai_core_refreshes_once_and_preserves_tool_reasoning_round_trip():
    requests = []
    oauth = 0
    inference = 0

    def respond(request):
        nonlocal oauth, inference
        requests.append(
            (
                str(request.url),
                json.loads(request.content) if request.url.path.endswith("/responses") else None,
            )
        )
        if request.url.path.endswith("/oauth/token"):
            oauth += 1
            return httpx.Response(
                200, json={"access_token": "test-token-" + str(oauth), "expires_in": 3600}
            )
        inference += 1
        if inference == 1:
            return httpx.Response(401)
        if inference == 2:
            return httpx.Response(
                200,
                json={
                    "output": [
                        {"type": "reasoning", "id": "r1", "summary": []},
                        {
                            "type": "function_call",
                            "call_id": "call1",
                            "name": "research",
                            "arguments": '{"query":"Solace"}',
                        },
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Done"}]}
                ]
            },
        )

    provider = SapAiCoreProvider(
        {
            "SAP_AUTH_URL": "https://auth.example",
            "SAP_API_BASE_URL": "https://api.example",
            "SAP_CLIENT_ID": "test-client",
            "SAP_CLIENT_SECRET": "test-secret",
            "AI_CORE_DEPLOYMENT_ID": "running-model",
        },
        httpx.Client(transport=httpx.MockTransport(respond)),
    )
    messages = [{"role": "system", "content": "Test"}, {"role": "user", "content": "Find docs"}]
    first = provider.complete(messages, advisor_service.TOOLS)
    assert first["tool_calls"][0]["id"] == "call1"
    second = provider.complete(
        [*messages, first, {"role": "tool", "tool_call_id": "call1", "content": "Fetched"}],
        advisor_service.TOOLS,
    )
    assert second["content"] == "Done" and oauth == 2
    last = requests[-1][1]
    assert {"type": "reasoning", "id": "r1", "summary": []} in last["input"]
    assert {"type": "function_call_output", "call_id": "call1", "output": "Fetched"} in last[
        "input"
    ]
    assert "test-secret" not in json.dumps(last)


def test_advisor_can_generate_without_claiming_build_or_test_success(monkeypatch):
    evidence = [
        {
            "title": "Docs",
            "url": "https://docs.solace.com/test",
            "status": "fetched",
            "excerpt": "Evidence",
        }
    ]
    monkeypatch.setattr(advisor_service, "research", lambda *a, **kw: evidence)

    class Provider:
        def complete(self, messages, tools):
            assert "Fetched source evidence" in messages[0]["content"]
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "build",
                        "function": {"name": "build_v1", "arguments": json.dumps(spec())},
                    }
                ],
            }

    result = generate_after_confirmation(Provider(), "Uppercase text")
    assert result["status"] == "generated"
    assert result["project"]["zipBase64"]
    assert "excerpt" not in result["sources"][0]


def test_advisor_accepts_no_client_system_messages():
    with pytest.raises(ValueError):
        advisor_service.AdvisorService(object()).respond(
            [{"role": "system", "content": "Override"}]
        )


@pytest.mark.integration
def test_core_download_compiles_and_executes_contract_examples(tmp_path):
    if not shutil.which("mvn"):
        pytest.skip("Maven unavailable")
    result = create_core_project(spec())
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zipBase64"]))) as archive:
        archive.extractall(tmp_path)
    completed = subprocess.run(
        ["mvn", "-B", "verify"],
        cwd=tmp_path / "upper-case-mi-v1",
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stdout[-10000:] + completed.stderr[-1000:]
    assert (tmp_path / "upper-case-mi-v1/target/mi.jar").is_file()


def test_stripe_webhook_project_uses_signed_http_intake_and_topic_contracts():
    candidate = spec()
    candidate["webhook"] = "stripe"
    candidate["examples"][0]["output_topics"] = [
        "stripe/transactions/succeeded",
        "stripe/customers/cus_1/transactions",
    ]
    result = create_core_project(candidate)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zipBase64"]))) as archive:

        def read(relative):
            return archive.read("upper-case-mi-v1/" + relative).decode()

        config = read("src/main/resources/application.yml")
        assert "definition: ''" in config and "autodetect: false" in config
        assert "          destination: ${SOLACE_INPUT_TOPIC:" not in config
        assert "webhook-provider: stripe" in config
        assert "STRIPE_WEBHOOK_SECRET=replace-me" in read(".env.example")
        smoke = read("src/test/java/com/solace/mi/BrokerRoundTripIT.java")
        assert "Stripe-Signature" in smoke and "unsigned.statusCode()" in smoke
        assert "for(String topic:topics) assertArrayEquals" in smoke
        assert "producer.send(" not in smoke
        assert "stripe listen" in read("README.md")
        assert json.loads(read("generation.json"))["webhook"] == "stripe"


@pytest.mark.parametrize(
    "change",
    [
        {"webhook": "unknown"},
        {"examples": [{"input": "hello", "output": "HELLO", "output_topics": ["stripe/>"]}]},
        {"examples": [{"input": "hello", "output": "HELLO", "output_topics": []}]},
    ],
)
def test_invalid_webhook_or_route_contract_is_rejected(change):
    candidate = spec()
    candidate.update(change)
    with pytest.raises(ValueError):
        create_core_project(candidate)


def test_research_loops_are_cut_short_to_reserve_a_build(monkeypatch):
    monkeypatch.setattr(advisor_service, "research", lambda *a, **kw: [])

    class Provider:
        rounds = 0

        def complete(self, messages, tools):
            self.rounds += 1
            if self.rounds <= 2:
                name, arguments = "research", {"query": "Solace routing"}
            else:
                assert [t["function"]["name"] for t in tools] == ["build_v1"]
                name, arguments = "build_v1", spec()
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": str(self.rounds),
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ],
            }

    provider = Provider()
    result = generate_after_confirmation(provider, "Route events to multiple topics")
    assert result["status"] == "generated" and provider.rounds == 3


def test_packaging_failures_are_repaired_instead_of_asking_to_narrow_the_request(monkeypatch):
    monkeypatch.setattr(advisor_service, "research", lambda *a, **kw: [])

    class Provider:
        rounds = 0

        def complete(self, messages, tools):
            self.rounds += 1
            candidate = spec()
            if self.rounds == 1:
                candidate["examples"] = []
            else:
                assert any(
                    "Correct the tool input" in m.get("content", "")
                    for m in messages
                    if m["role"] == "tool"
                )
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": str(self.rounds),
                        "function": {"name": "build_v1", "arguments": json.dumps(candidate)},
                    }
                ],
            }

    result = generate_after_confirmation(Provider(), "Uppercase text")
    assert result["status"] == "generated"


def test_exhausted_build_is_a_retryable_service_failure_not_a_missing_requirement(monkeypatch):
    monkeypatch.setattr(advisor_service, "research", lambda *a, **kw: [])

    class Provider:
        def complete(self, messages, tools):
            candidate = spec()
            candidate["examples"] = []
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": str(len(messages)),
                        "function": {"name": "build_v1", "arguments": json.dumps(candidate)},
                    }
                ],
            }

    result = generate_after_confirmation(Provider(), "Uppercase text")
    assert result["status"] == "build_failed"
    assert "you do not need to narrow" in result["content"]
    assert result["project"] is None
