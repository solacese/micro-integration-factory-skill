from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec2event.services import advisor_service, service_confirmation

REQUEST = "listen to Stripe webhooks and post customer transactions to multiple Solace topics"


def evidence(url="https://docs.stripe.com/webhooks.md"):
    return {
        "url": url,
        "status": "fetched",
        "title": "Official documentation",
        "fetchedAt": "2026-11-04T12:00:00+00:00",
        "sha256": "a" * 64,
        "excerpt": "Official API and protocol documentation. " * 10,
    }


@pytest.fixture
def research(monkeypatch):
    calls = []
    monkeypatch.setattr(advisor_service, "research", lambda *a, **kw: [evidence()])

    def fetch(url, title="Documentation"):
        calls.append(url)
        return evidence(url)

    monkeypatch.setattr(service_confirmation, "fetch_reference", fetch)
    monkeypatch.setattr(advisor_service, "fetch_reference", fetch)
    return calls


class NoGeneration:
    def complete(self, messages, tools):
        pytest.fail("The model must not generate code before service confirmation")


def test_stripe_is_verified_and_proposed_before_any_code_generation(research):
    result = advisor_service.AdvisorService(NoGeneration()).respond(
        [{"role": "user", "content": REQUEST}]
    )
    assert result["status"] == "awaiting_confirmation"
    assert result["project"] is None and result["confirmationToken"]
    assert "https://docs.stripe.com/webhooks" in result["content"]
    assert "Inbound HTTPS webhooks" in result["content"]
    assert "no Stripe SDK is needed" in result["content"]
    assert "https://docs.stripe.com/webhooks.md" in research


def test_plain_yes_uses_the_original_request_and_confirmed_api(research):
    service = advisor_service.AdvisorService(NoGeneration())
    first = service.respond([{"role": "user", "content": REQUEST}])
    candidate = json.loads(
        (Path(__file__).parents[1] / "resources/samples/core-java/stripe-webhook.json").read_text()
    )

    class Builder:
        def complete(self, messages, tools):
            assert "User-confirmed service/API plan" in messages[0]["content"]
            assert any(
                REQUEST in message["content"] for message in messages if message["role"] == "user"
            )
            assert tools[0]["function"]["name"] == "build_v1"
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "build",
                        "function": {"name": "build_v1", "arguments": json.dumps(candidate)},
                    }
                ],
            }

    service.provider = Builder()
    result = service.respond(
        [
            {"role": "user", "content": REQUEST},
            {"role": "assistant", "content": first["content"]},
            {"role": "user", "content": "yes"},
        ],
        confirmation_token=first["confirmationToken"],
    )
    assert result["status"] == "generated" and result["project"]["zipBase64"]
    assert "https://docs.stripe.com/webhooks.md" in [s["url"] for s in result["sources"]]


def test_yes_without_receipt_does_not_generate(research):
    result = advisor_service.AdvisorService(NoGeneration()).respond(
        [
            {"role": "user", "content": REQUEST},
            {"role": "user", "content": "yes"},
        ]
    )
    assert result["status"] == "awaiting_confirmation" and result["project"] is None


def test_expired_or_tampered_confirmation_is_not_an_approval(research, monkeypatch):
    service = advisor_service.AdvisorService(NoGeneration())
    first = service.respond([{"role": "user", "content": REQUEST}])
    history = [{"role": "user", "content": REQUEST}, {"role": "user", "content": "yes"}]
    assert (
        service.respond(history, confirmation_token=first["confirmationToken"] + "x")["status"]
        == "awaiting_confirmation"
    )
    original_time = service_confirmation.time.time()
    monkeypatch.setattr(service_confirmation.time, "time", lambda: original_time + 1801)
    assert (
        service.respond(history, confirmation_token=first["confirmationToken"])["status"]
        == "awaiting_confirmation"
    )


def test_replacement_vendor_and_changed_core_need_their_own_confirmation(research):
    service = advisor_service.AdvisorService(NoGeneration())
    first = service.respond([{"role": "user", "content": REQUEST}])
    replacement = service.respond(
        [
            {"role": "user", "content": REQUEST},
            {"role": "assistant", "content": first["content"]},
            {
                "role": "user",
                "content": "No, use Salesforce REST to create Account records instead",
            },
        ],
        confirmation_token=first["confirmationToken"],
    )
    assert replacement["status"] == "awaiting_confirmation"
    assert [s["name"] for s in replacement["servicePlan"]["services"]] == ["Salesforce REST API"]
    assert "Java 17 HttpClient" in replacement["content"]
    assert (
        service.respond(
            [{"role": "user", "content": REQUEST}, {"role": "user", "content": "yes"}],
            previous_core="changed core",
            confirmation_token=first["confirmationToken"],
        )["status"]
        == "awaiting_confirmation"
    )


def test_salesforce_event_subscriptions_are_not_presented_as_webhooks(research):
    service = advisor_service.AdvisorService(NoGeneration())
    history = [
        {"role": "user", "content": "Subscribe to Salesforce CDC and publish changes to Solace"}
    ]
    result = service.respond(history)
    assert result["status"] == "needs_input" and result["project"] is None
    assert "gRPC over HTTP/2" in result["content"] and "not HTTP webhooks" in result["content"]
    assert not result.get("confirmationToken")
    # A short refinement keeps the vendor but switches the API intentionally.
    history += [
        {"role": "assistant", "content": result["content"]},
        {"role": "user", "content": "Use REST to query Account records instead"},
    ]
    result = service.respond(history)
    assert result["status"] == "awaiting_confirmation"
    assert result["servicePlan"]["services"][0]["name"] == "Salesforce REST API"


def test_unavailable_official_docs_do_not_lead_to_a_confirmable_unverified_plan(
    research, monkeypatch
):
    monkeypatch.setattr(
        service_confirmation, "fetch_reference", lambda *a: {"status": "unavailable"}
    )
    result = advisor_service.AdvisorService(NoGeneration()).respond(
        [{"role": "user", "content": REQUEST}]
    )
    assert result["status"] == "needs_input" and not result.get("confirmationToken")
    assert "could not read the official documentation" in result["content"]


def test_multi_service_plan_does_not_mistake_listening_to_stripe_for_salesforce_subscriptions(
    research,
):
    result = advisor_service.AdvisorService(NoGeneration()).respond(
        [
            {
                "role": "user",
                "content": "Listen to Stripe webhooks and post transactions to Salesforce REST Account records",
            }
        ]
    )
    assert result["status"] == "awaiting_confirmation"
    assert [s["name"] for s in result["servicePlan"]["services"]] == [
        "Stripe Webhooks",
        "Salesforce REST API",
    ]


def test_receipts_survive_workers_with_the_same_configured_key(monkeypatch):
    monkeypatch.setenv("FACTORY_CONFIRMATION_KEY", "fixture-key-only")
    plan = {"services": [], "sources": []}
    token = service_confirmation.seal(plan, "request", "")
    monkeypatch.setattr(service_confirmation, "_LOCAL_KEY", b"other-worker-key")
    assert service_confirmation.unseal(token, "request", "") == plan
    assert service_confirmation.unseal(token, "changed request", "") is None
    monkeypatch.setenv("FACTORY_CONFIRMATION_KEY", "changed-key")
    assert service_confirmation.unseal(token, "request", "") is None


def test_no_research_or_generation_loop_beyond_five_user_turns(research):
    history = [{"role": "user", "content": REQUEST}] + [
        {"role": "user", "content": "No, another Stripe webhook mapping"}
    ] * 5
    result = advisor_service.AdvisorService(NoGeneration()).respond(history)
    assert result["project"] is None and not result.get("confirmationToken")
    assert "five conversational steps" in result["content"]


def test_fifth_user_turn_can_confirm_and_finish_the_draft(research):
    history = [{"role": "user", "content": REQUEST}] + [
        {"role": "user", "content": detail}
        for detail in [
            "Use default topics",
            "Preserve the raw JSON bytes",
            "Use unknown for a missing customer",
        ]
    ]
    service = advisor_service.AdvisorService(NoGeneration())
    proposal = service.respond(history)
    assert proposal["status"] == "awaiting_confirmation"
    candidate = json.loads(
        (Path(__file__).parents[1] / "resources/samples/core-java/stripe-webhook.json").read_text()
    )

    class Builder:
        def complete(self, messages, tools):
            assert any(
                "Preserve the raw JSON bytes" in message["content"]
                for message in messages
                if message["role"] == "user"
            )
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "build",
                        "function": {"name": "build_v1", "arguments": json.dumps(candidate)},
                    }
                ],
            }

    service.provider = Builder()
    result = service.respond(
        history
        + [
            {"role": "assistant", "content": proposal["content"]},
            {"role": "user", "content": "yes"},
        ],
        confirmation_token=proposal["confirmationToken"],
    )
    assert result["status"] == "generated"
    import base64
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["project"]["zipBase64"]))) as archive:
        metadata = next(name for name in archive.namelist() if name.endswith("/generation.json"))
        assert (
            json.loads(archive.read(metadata))["confirmedServicePlan"][0]["name"]
            == "Stripe Webhooks"
        )


def test_discovery_cannot_call_the_generation_tool(research):
    class PrematureBuilder:
        def complete(self, messages, tools):
            assert all(tool["function"]["name"] != "build_v1" for tool in tools)
            return {
                "role": "assistant",
                "tool_calls": [{"id": "bad", "function": {"name": "build_v1", "arguments": "{}"}}],
            }

    result = advisor_service.AdvisorService(PrematureBuilder()).respond(
        [{"role": "user", "content": "Connect another vendor API to Solace"}]
    )
    assert result["project"] is None and not result.get("confirmationToken")


def test_vendor_source_verifies_salesforce_when_doc_pages_reject_server_requests(
    research, monkeypatch
):
    def fetch(url, title="Documentation"):
        if "developer.salesforce.com" in url:
            return {"url": url, "status": "unavailable", "reason": "HTTPStatusError"}
        return evidence(url)

    monkeypatch.setattr(service_confirmation, "fetch_reference", fetch)
    result = advisor_service.AdvisorService(NoGeneration()).respond(
        [{"role": "user", "content": "Create Salesforce Account records using REST"}]
    )
    assert result["status"] == "awaiting_confirmation" and result["project"] is None
    service = result["servicePlan"]["services"][0]
    assert service["documentation"].startswith("https://developer.salesforce.com/")
    assert service["verificationUrl"].startswith("https://raw.githubusercontent.com/forcedotcom/")
    assert "Verified vendor reference" in result["content"]
