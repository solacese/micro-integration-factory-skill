"""Bounded research of primary documentation, with fetched evidence and provenance."""

from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urlsplit

import httpx

CATALOG = [
    (
        "Go AMQP 1.0 messaging client",
        "https://raw.githubusercontent.com/Azure/go-amqp/main/README.md",
    ),
    (
        "Go YAML shared configuration parser",
        "https://raw.githubusercontent.com/yaml/go-yaml/main/README.md",
    ),
    (
        "Solace micro integrations overview",
        "https://docs.solace.com/Micro-Integrations/Micro-Integrations.htm",
    ),
    (
        "Solace micro integration Spring Cloud Stream SDK",
        "https://raw.githubusercontent.com/SolaceProducts/solace-spring-cloud/master/README.md",
    ),
    (
        "Solace MDK published release versions",
        "https://repo.maven.apache.org/maven2/com/solace/microintegration/core/micro-integration-build-parent/maven-metadata.xml",
    ),
    (
        "Proven schema registry MI JSON XML XSD Avro Protobuf installation",
        "https://raw.githubusercontent.com/solacese/schema-validation-micro-integration/main/README.md",
    ),
    (
        "Solace schema registry deployment authentication",
        "https://docs.solace.com/Schema-Registry/deploying-schema-registry-docker.htm",
    ),
    (
        "Solace schema registry overview JSON XML Avro Protobuf",
        "https://docs.solace.com/Schema-Registry/schema-registry-overview.htm",
    ),
    (
        "Solace REST messaging headers payload delivery",
        "https://docs.solace.com/API/RESTMessagingPrtl/Solace-REST-Message-Encoding.htm",
    ),
    (
        "Solace Spring Cloud Stream binder",
        "https://raw.githubusercontent.com/SolaceProducts/solace-spring-cloud/master/README.md",
    ),
    ("Stripe webhook setup retries snapshot events", "https://docs.stripe.com/webhooks.md"),
    (
        "Salesforce REST API records query create update OAuth",
        "https://developer.salesforce.com/docs/platform/api-rest/guide/intro-rest.md",
    ),
    (
        "Salesforce Pub/Sub API CDC platform events gRPC Avro",
        "https://developer.salesforce.com/docs/platform/pub-sub-api/guide/intro.md",
    ),
    (
        "Stripe webhook signatures raw payload timestamp HMAC",
        "https://raw.githubusercontent.com/stripe/stripe-java/master/src/main/java/com/stripe/net/Webhook.java",
    ),
    (
        "PostgreSQL logical decoding CDC replication",
        "https://www.postgresql.org/docs/current/logicaldecoding.html",
    ),
    ("Apache Kafka consumers delivery semantics", "https://kafka.apache.org/documentation/"),
    (
        "Docker Compose installation health wait",
        "https://docs.docker.com/compose/how-tos/startup-order/",
    ),
    (
        "Spring Cloud Stream dynamic destinations StreamBridge",
        "https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html",
    ),
    (
        "Jackson Java JSON databinding API",
        "https://raw.githubusercontent.com/FasterXML/jackson-databind/3.x/README.md",
    ),
    (
        "JSON schema networknt validator API",
        "https://raw.githubusercontent.com/networknt/json-schema-validator/master/README.md",
    ),
]
HOSTS = {
    "docs.solace.com",
    "docs.stripe.com",
    "www.postgresql.org",
    "kafka.apache.org",
    "docs.docker.com",
    "docs.spring.io",
    "repo.maven.apache.org",
    "developer.salesforce.com",
    "docs.oracle.com",
    "go.dev",
    "pkg.go.dev",
}
GITHUB_ORGS = {
    "SolaceProducts",
    "SolaceSamples",
    "solacecommunity",
    "spring-cloud",
    "apache",
    "stripe",
    "FasterXML",
    "networknt",
    "protocolbuffers",
    "forcedotcom",
    "salesforce",
    "Azure",
    "yaml",
    "golang",
    "santhosh-tekuri",
    "linkedin",
}
MAX_BYTES = 600_000
_cache: dict[str, tuple[float, dict]] = {}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "header", "footer"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def allowed_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in {443, None}
        ):
            return False
        if re.search(
            r"(?:^|&)(?:access_token|api_key|token|password|secret|key)=", parsed.query, re.I
        ):
            return False
        if parsed.hostname in HOSTS:
            return True
        if parsed.hostname in {"github.com", "raw.githubusercontent.com"}:
            parts = parsed.path.strip("/").split("/")
            return bool(
                parts
                and (
                    parts[0] in GITHUB_ORGS
                    or parts[:2] == ["solacese", "schema-validation-micro-integration"]
                )
            )
    except ValueError:
        pass
    return False


def fetch_reference(url: str, title: str = "Primary documentation") -> dict:
    if not allowed_url(url):
        return {
            "url": url,
            "status": "blocked",
            "reason": "Use a supported primary documentation host",
        }
    cached = _cache.get(url)
    if cached and time.monotonic() - cached[0] < 1800:
        return dict(cached[1])
    original = url
    try:
        with httpx.Client(
            timeout=httpx.Timeout(8, connect=3),
            headers={
                "User-Agent": "Solace-MI-Factory/1.0",
                "Accept": "text/markdown, text/html;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        ) as client:
            for _ in range(4):
                if not allowed_url(url):
                    raise ValueError("Redirect leaves primary documentation hosts")
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = str(response.url.join(response.headers["location"]))
                        continue
                    response.raise_for_status()
                    if re.search(r"(?:not[-_]?found|/404)(?:[./?]|$)", str(response.url), re.I):
                        raise ValueError("Documentation redirected to a soft 404 page")
                    chunks = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    text = raw.decode("utf-8", errors="replace")
                    if "text/html" in response.headers.get("content-type", ""):
                        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
                        page_title = (
                            re.sub(r"\s+", " ", title_match.group(1)).strip().lower()
                            if title_match
                            else ""
                        )
                        if page_title.startswith(
                            ("404", "not found", "page not found", "sorry, it looks")
                        ):
                            raise ValueError("Documentation returned a soft 404 page")
                        parser = _Text()
                        parser.feed(text)
                        text = "\n".join(parser.parts)
                    if original.endswith("maven-metadata.xml"):
                        root = ET.fromstring(text)
                        text = (
                            "Published MDK release: "
                            + str(root.findtext("versioning/release"))
                            + "\n"
                            + text[-5000:]
                        )
                    result = {
                        "title": title,
                        "url": url,
                        "status": "fetched",
                        "fetchedAt": datetime.now(UTC).isoformat(),
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "excerpt": text[:5500],
                    }
                    _cache[original] = (time.monotonic(), result)
                    return dict(result)
            raise ValueError("Too many redirects")
    except Exception as error:
        print(
            json.dumps(
                {
                    "event": "reference_unavailable",
                    "host": urlsplit(original).hostname,
                    "reason": type(error).__name__,
                    "httpStatus": error.response.status_code
                    if isinstance(error, httpx.HTTPStatusError)
                    else None,
                }
            )
        )
        return {
            "title": title,
            "url": original,
            "status": "unavailable",
            "reason": type(error).__name__,
        }


def research(query: str, limit=4) -> list[dict]:
    query = query[:400]
    words = set(re.findall(r"[a-z0-9]+", query.lower())) - {
        "the",
        "and",
        "with",
        "from",
        "create",
        "build",
        "integration",
    }
    ranked = sorted(
        CATALOG,
        key=lambda item: len(words & set(re.findall(r"[a-z0-9]+", item[0].lower()))),
        reverse=True,
    )
    candidates = list(ranked[:limit])
    if "stripe" in words:
        # Keep vendor setup, signature implementation, and actual routing APIs together.
        candidates = [item for item in CATALOG if item[0].startswith("Stripe")]
        candidates += [
            item for item in CATALOG if item[0].startswith("Spring Cloud Stream dynamic")
        ]
        candidates = candidates[:limit]
    elif "salesforce" in words:
        candidates = [item for item in ranked if item[0].startswith("Salesforce")][:limit]
    # Search adds discovery beyond the catalog; only verified primary-host pages
    # can enter evidence. Search snippets themselves are never treated as facts.
    try:
        # Search only technical terms, never raw user payloads, credentials, or
        # private business descriptions entered into the chat.
        technologies = [
            term
            for term in [
                "Java",
                "JSON",
                "XML",
                "XSD",
                "Avro",
                "Protobuf",
                "Kafka",
                "PostgreSQL",
                "Stripe",
                "Salesforce",
                "MQTT",
                "REST",
                "schema registry",
                "MDK",
                "Spring Cloud Stream",
            ]
            if re.search(r"\b" + re.escape(term) + r"\b", query, re.I)
        ]
        search_query = (
            "Solace "
            + " ".join(technologies[:6] or ["micro integration"])
            + " documentation site:docs.solace.com"
        )
        if "stripe" in words:
            search_query = "Stripe webhooks signature documentation site:docs.stripe.com"
        elif "salesforce" in words:
            search_query = "Salesforce API documentation REST Pub/Sub site:developer.salesforce.com"
        r = httpx.get(
            "https://www.bing.com/search?" + urlencode({"format": "rss", "q": search_query}),
            timeout=4,
        )
        if r.status_code == 200:
            for item in ET.fromstring(r.text).findall("./channel/item"):
                url = item.findtext("link", "")
                if allowed_url(url) and url not in {p[1] for p in candidates}:
                    # Curated vendor references are already direct primary sources.
                    if not {"stripe", "salesforce"} & words:
                        candidates.insert(0, (item.findtext("title", "Documentation"), url))
                    break
    except Exception:
        pass
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda item: fetch_reference(item[1], item[0]), candidates[:limit]))
