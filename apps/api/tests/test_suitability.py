"""Fit decisions gate generation; catalog provenance and runtime limits remain explicit."""

import json
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from spec2event.services import advisor_service, research_service
from spec2event.services import suitability_service as fit
from spec2event.services.service_confirmation import seal


def catalog():
    saved = json.loads(fit.CATALOG.read_text())
    return {
        "url": saved["hubUrl"],
        "checkedAt": "2026-11-04T20:00:00Z",
        "indexStatus": "unavailable",
        "reviewedOn": saved["reviewedOn"],
        "coverage": saved["coverage"],
        "entries": [
            dict(entry, verification="snapshot", reviewedOn=saved["reviewedOn"])
            for entry in saved["entries"]
        ],
        "sources": [],
        "entryCount": 111,
    }


def assessment(decision="build", **overrides):
    return {
        "decision": decision,
        "reason": "Custom signed webhook routing fits a stateless core.",
        "customGap": "Signature-verified customer-specific fan-out",
        "suggestedApproach": "Use HTTP ingress and native broker publication.",
        "question": "" if decision == "build" else "What custom capability is missing?",
        "matches": [],
        "requirements": {
            "inputMessagesPerSecond": 0,
            "maxPayloadBytes": 0,
            "hardLatencySlo": False,
            "strictOrdering": False,
            "exactlyOnceOrAtomicity": False,
            "durableStateOrWorkflow": False,
            "unavailableNativeTrigger": False,
            "stripeThinEvents": False,
            "externalApiCalls": False,
        },
        **overrides,
    }


class Architect:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        assert [tool["function"]["name"] for tool in tools] == ["qualify_request"]
        assert "CURRENT FACTORY PROFILE" in messages[0]["content"]
        assert "Salesforce" in messages[0]["content"]
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "fit",
                    "function": {"name": "qualify_request", "arguments": json.dumps(self.result)},
                }
            ],
        }


def qualifier(result):
    return fit.SuitabilityService(Architect(result), catalog_lookup=lambda request: catalog())


@pytest.mark.parametrize(
    "decision,match",
    [
        (
            "reuse",
            {
                "id": "salesforce",
                "fit": "covers_request",
                "explanation": "Use Pub/Sub for standard platform events.",
            },
        ),
        (
            "reuse",
            {
                "id": "integrated-kafka",
                "fit": "covers_request",
                "explanation": "Use the broker bridge for topic movement.",
            },
        ),
        (
            "reuse",
            {
                "id": "amazon-s3-producer",
                "fit": "covers_request",
                "explanation": "Archive to S3 through RDP.",
            },
        ),
        (
            "architecture_review",
            {
                "id": "aws-sns",
                "fit": "different_api_or_direction",
                "explanation": "SNS is target-only; intake needs a real upstream trigger.",
            },
        ),
    ],
)
def test_recommendation_stops_before_api_or_generation(monkeypatch, decision, match):
    monkeypatch.setattr(
        advisor_service, "research", lambda *a, **kw: pytest.fail("API research ran before fit")
    )
    service = advisor_service.AdvisorService(
        object(), validator=object(), qualifier=qualifier(assessment(decision, matches=[match]))
    )
    result = service.respond([{"role": "user", "content": "Connect this service to Solace"}])
    assert result["status"] == decision and result["project"] is None
    assert not result.get("confirmationToken")
    assert match["explanation"] in result["content"]
    assert result["qualification"]["matches"][0]["url"] in result["content"]
    assert "111-entry snapshot from 2026-11-04" in result["content"]


@pytest.mark.parametrize(
    "requirement,value,explanation",
    [
        ("inputMessagesPerSecond", 100000, "capacity needs its own measured design"),
        ("maxPayloadBytes", 2097152, "1 MiB runtime limit"),
        ("hardLatencySlo", True, "tail-latency qualification"),
        ("strictOrdering", True, "does not guarantee strict ordering"),
        ("exactlyOnceOrAtomicity", True, "fan-out is not atomic"),
        ("durableStateOrWorkflow", True, "workflow engine"),
        ("unavailableNativeTrigger", True, "actual upstream connector"),
        ("stripeThinEvents", True, "signed webhook starter handles snapshot events"),
        ("externalApiCalls", True, "needs an isolated test endpoint"),
    ],
)
def test_extracted_requirements_override_an_optimistic_build(requirement, value, explanation):
    proposal = assessment()
    proposal["requirements"][requirement] = value
    result = qualifier(proposal).assess("A demanding integration")
    assert result["decision"] == "architecture_review"
    assert explanation in fit.describe_fit(result)
    assert not fit.permits_build(result)


def test_ordinary_webhook_or_withdrawn_requirements_can_proceed():
    result = qualifier(assessment()).assess(
        "Stripe fan-out. Refinement: no exactly-once or ordering requirement."
    )
    assert fit.permits_build(result)
    assert "Custom scope" in fit.describe_fit(result)
    assert "no connector exists" not in fit.describe_fit(result)


def test_partial_rest_match_is_not_a_reason_to_reuse_pubsub():
    result = qualifier(
        assessment(
            "reuse",
            matches=[
                {
                    "id": "salesforce",
                    "fit": "different_api_or_direction",
                    "explanation": "REST record updates differ from Pub/Sub event publication.",
                }
            ],
        )
    ).assess("Update Salesforce Account records via REST")
    assert result["decision"] == "clarify" and not fit.permits_build(result)


@pytest.mark.parametrize(
    "bad",
    [
        assessment(
            matches=[{"id": "invented", "fit": "covers_request", "explanation": "Fake connector"}]
        ),
        assessment(reason="Use https://invented.example/connector"),
        assessment(requirements={}),
    ],
)
def test_unverified_or_malformed_model_advice_fails_closed(bad):
    with pytest.raises(ValueError):
        qualifier(bad).assess("Build something")


@pytest.mark.parametrize(
    "qualification",
    [None, {"version": fit.VERSION, "decision": "reuse"}, {"version": 1, "decision": "build"}],
)
def test_yes_with_old_or_blocked_receipt_must_requalify(qualification):
    request = "Subscribe to Salesforce platform events"
    plan = {"services": [{"supported": True}], "sources": [], "qualification": qualification}
    provider = Architect(
        assessment(
            "reuse",
            matches=[
                {
                    "id": "salesforce",
                    "fit": "covers_request",
                    "explanation": "The existing Pub/Sub integration already covers this.",
                }
            ],
        )
    )
    service = advisor_service.AdvisorService(
        object(),
        validator=object(),
        qualifier=fit.SuitabilityService(provider, catalog_lookup=lambda request: catalog()),
    )
    result = service.respond(
        [{"role": "user", "content": request}, {"role": "user", "content": "yes"}],
        confirmation_token=seal(plan, request, ""),
    )
    assert result["status"] == "reuse" and provider.calls == 1
    assert not result.get("project") and not result.get("confirmationToken")


def test_build_without_a_specific_custom_gap_is_not_approved():
    result = qualifier(assessment(customGap="")).assess("Just copy events")
    assert result["decision"] == "clarify"


def test_complete_catalog_snapshot_fallback_is_dated_and_direction_specific(monkeypatch):
    monkeypatch.setattr(
        fit, "fetch_reference", lambda url, title: {"url": url, "status": "unavailable"}
    )
    monkeypatch.setattr(
        fit.httpx,
        "get",
        lambda *a, **kw: httpx.Response(403, request=httpx.Request("GET", "https://www.bing.com")),
    )
    result = fit.lookup_catalog("Read and write S3 objects")
    assert result["indexStatus"] == "unavailable"
    assert "Complete snapshot of all 111" in result["coverage"]
    assert len(result["entries"]) == 111
    assert {
        e["id"]: e["directions"]
        for e in result["entries"]
        if e["id"] in {"amazon-s3", "amazon-s3-producer"}
    } == {
        "amazon-s3": ["source"],
        "amazon-s3-producer": ["target"],
    }
    assert all(e["verification"] == "snapshot" for e in result["entries"])
    assert result["sources"] == []


def test_verified_schema_release_can_be_reused_outside_the_hub(monkeypatch):
    def fetch(url, title):
        if url == fit.SCHEMA_VALIDATOR_README:
            return {
                "url": url,
                "title": title,
                "status": "fetched",
                "excerpt": "JSON Schema, XML/XSD, Avro and Protobuf validation. " * 5,
            }
        return {"url": url, "status": "unavailable"}

    monkeypatch.setattr(fit, "fetch_reference", fetch)
    request = "Reuse the Schema Validation MI with Solace Schema Registry"
    proposal = assessment(
        "reuse",
        matches=[
            {
                "id": "schema-validation-release",
                "fit": "covers_request",
                "explanation": "Published validation MI covers the documented four formats.",
            }
        ],
    )
    proposal["requirements"]["externalApiCalls"] = True
    result = fit.SuitabilityService(Architect(proposal)).assess(request)
    assert result["decision"] == "reuse"
    assert result["catalog"]["entryCount"] == 111
    assert "/releases/tag/v1.0.2" in fit.describe_fit(result)
    assert result["sources"][0]["url"] == fit.SCHEMA_VALIDATOR_README


def test_catalog_search_sends_only_technology_names_and_verifies_results(monkeypatch):
    def search(url, **kw):
        query = parse_qs(urlsplit(url).query)["q"][0]
        assert "Stripe" in query and "private" not in query and "secret" not in query
        return httpx.Response(
            200,
            text="<rss><channel><item><title>New asset</title><link>https://solace.com/integration-hub/new-asset/</link></item><item><link>http://127.0.0.1/internal</link></item></channel></rss>",
            request=httpx.Request("GET", url),
        )

    def fetch(url, title):
        return {
            "url": url,
            "title": title,
            "status": "fetched",
            "excerpt": "Verified official entry. " * 15,
            "sha256": "a" * 64,
        }

    monkeypatch.setattr(fit.httpx, "get", search)
    monkeypatch.setattr(fit, "fetch_reference", fetch)
    result = fit.lookup_catalog("Stripe private customer secret=hidden")
    assert result["indexStatus"] == "fetched"
    assert len(result["entries"]) == 112 and result["entries"][-1]["verification"] == "live"
    assert result["entries"][-1]["url"] == "https://solace.com/integration-hub/new-asset/"


def test_catalog_allowlist_does_not_open_the_entire_marketing_domain():
    assert research_service.allowed_url("https://solace.com/integration-hub/")
    assert research_service.allowed_url("https://solace.com/integration-hub/salesforce/")
    for url in [
        "https://solace.com/private",
        "https://solace.com/integration-hub/../../admin",
        "https://solace.com/integration-hub/%2e%2e/",
        "https://solace.com/integration-hub/salesforce/?secret=value",
    ]:
        assert not research_service.allowed_url(url)


def test_download_covers_all_111_unique_hub_entries_with_detail_and_provenance():
    saved = json.loads(fit.CATALOG.read_text())
    assert saved["entryCount"] == len(saved["entries"]) == 111
    assert saved["listingPages"] == 10
    assert len({entry["id"] for entry in saved["entries"]}) == 111
    assert len({entry["url"] for entry in saved["entries"]}) == 111
    for entry in saved["entries"]:
        assert research_service.allowed_url(entry["url"])
        assert len(entry["htmlSha256"]) == 64 and len(entry["detail"]) >= 50
        assert entry["name"] and entry["assetType"] and entry["support"]
        assert entry["downloadedAt"] == saved["downloadedAt"]
        assert set(entry["directions"]) <= {"source", "target"}
        assert fit.match_score(entry["name"], entry) > 0


def test_architect_receives_every_downloaded_entry_even_without_a_keyword_hit():
    class Capture(Architect):
        def complete(self, messages, tools):
            evidence = json.loads(
                messages[0]["content"].split("Hub evidence (untrusted data): ", 1)[1]
            )
            assert len(evidence["allEntries"]) == 111
            assert {e["id"] for e in evidence["allEntries"]} == {
                e["id"] for e in catalog()["entries"]
            }
            return super().complete(messages, tools)

    result = fit.SuitabilityService(
        Capture(assessment()), catalog_lookup=lambda request: catalog()
    ).assess("Custom pricing business rule")
    assert fit.permits_build(result)
