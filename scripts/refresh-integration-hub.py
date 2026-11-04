#!/usr/bin/env python3
"""Download every paginated Hub listing and detail page; publish a count-checked snapshot.

Uses curl's system TLS/HTTP stack because the site may reject Python HTTP clients.
Raw pages stay in --cache; the runtime receives extracted content and SHA-256 provenance.
"""

import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HUB = "https://solace.com/integration-hub/"
REFRESH = "https://solace.com/wp-json/facetwp/v1/refresh"
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()

    def text(self):
        if self.tag in {"script", "style", "nav", "header", "footer", "noscript"}:
            return ""
        return re.sub(
            r"\s+",
            " ",
            " ".join(
                child.text() if isinstance(child, Node) else child
                for child in self.children
            ),
        ).strip()


class Document(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def get(url, cache, payload=None):
    if url != REFRESH and not re.fullmatch(
        r"https://solace\.com/integration-hub/(?:[a-z0-9-]+/)?", url
    ):
        raise ValueError("Only public Hub pages are downloaded")
    args = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--location",
        "--max-redirs",
        "2",
        "--max-time",
        "40",
        "--retry",
        "2",
        "--max-filesize",
        "6000000",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        url,
    ]
    if payload is not None:
        args += [
            "-H",
            "Content-Type: application/json",
            "-H",
            "Referer: " + HUB,
            "--data-binary",
            json.dumps(payload),
        ]
    raw = subprocess.check_output(args)
    cache.write_bytes(raw)
    return raw


def parse_cards(html):
    root = Document(html).root
    entries = []
    for card in root.walk():
        if not card.has_class("connectors"):
            continue
        link = next(
            n for n in card.walk() if n.tag == "a" and n.has_class("connector-content")
        )
        title = next(n.text() for n in card.walk() if n.tag == "h3")
        fields = {}
        for row in card.walk():
            if row.has_class("labels"):
                label, value = row.text().split(":", 1)
                fields[label.strip()] = value.strip().strip(",")
        url = link.attrs["href"]
        entries.append(
            {
                "id": urlsplit(url).path.strip("/").split("/")[-1],
                "name": title,
                "url": url,
                "assetType": fields.get("Asset Type", "Unspecified"),
                "directions": [
                    word.strip().lower()
                    for word in fields.get("Endpoint", "").split(",")
                    if word.strip()
                ],
                "support": fields.get("Support", "Unspecified"),
                "deployment": fields.get("Platform", "Unspecified"),
                "category": fields.get("Category", "Unspecified"),
            }
        )
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=ROOT / ".runtime/integration-hub-download"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "apps/api/resources/catalog/integration-hub.json",
    )
    parser.add_argument(
        "--expected-count", type=int, help="Fail closed if the site's total changed"
    )
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    existing = (
        json.loads(args.output.read_text()) if args.output.exists() else {"entries": []}
    )
    notes = {e["url"]: e for e in existing["entries"]}
    initial = get(HUB, args.cache / "index.html").decode()
    settings = json.loads(
        re.search(r"window.FWP_JSON = (.*?);\s*</script>", initial, re.S).group(1)
    )
    pager = settings["preload_data"]["settings"]["pager"]
    total, pages = pager["total_rows"], pager["total_pages"]
    if (
        total > 1000
        or pages > 100
        or (args.expected_count is not None and total != args.expected_count)
    ):
        raise ValueError(f"Unexpected Hub count: {total} entries / {pages} pages")
    entries = parse_cards(initial)
    print(f"Hub lists {total} results over {pages} pages", flush=True)
    for page in range(2, pages + 1):
        payload = {
            "action": "facetwp_refresh",
            "data": {
                "facets": {
                    "connectors_search": "",
                    **{
                        key: []
                        for key in [
                            "connectors_asset_type",
                            "connector_type",
                            "connectors_endpoint",
                            "connector_licenses",
                            "connectors_platform",
                            "connectors_sort_by",
                            "connectors_all",
                        ]
                    },
                },
                "http_params": {"get": {}, "uri": "integration-hub", "url_vars": []},
                "template": "connectors_archive",
                "extras": {"pager": True, "sort": "default"},
                "soft_refresh": 1,
                "first_load": 0,
                "paged": str(page),
            },
        }
        data = json.loads(get(REFRESH, args.cache / f"page-{page}.json", payload))
        if data["settings"]["pager"]["total_rows"] != total:
            raise ValueError("Hub changed during pagination; retry the snapshot")
        entries.extend(
            parse_cards(
                data["template"]
                .replace(r"\"", '"')
                .replace(r"\/", "/")
                .replace(r"\n", "\n")
            )
        )
        print(f"Page {page}: {len(entries)}/{total}", flush=True)
    if len(entries) != total or len({e["url"] for e in entries}) != total:
        raise ValueError(
            f"Incomplete or duplicate Hub download: {len(entries)} / {total}"
        )
    downloaded = datetime.now(UTC).isoformat()

    def detail(entry):
        raw = get(entry["url"], args.cache / (entry["id"] + ".html"))
        doc = Document(raw.decode(errors="replace")).root
        area = next((n for n in doc.walk() if n.has_class("connector-details")), None)
        if area is None or len(area.text()) < 50:
            raise ValueError("Missing detail content for " + entry["url"])
        summary = next(
            (n.text() for n in area.walk() if n.has_class("conn-content")), ""
        )
        if not summary:
            summary = area.text()
        prior = notes.get(entry["url"], {})
        aliases = list(
            dict.fromkeys(
                [
                    entry["name"].lower(),
                    entry["id"].replace("-", " "),
                    *prior.get("aliases", []),
                ]
            )
        )
        words = re.findall(r"[a-z0-9]+", entry["name"].lower())
        aliases += [
            w
            for w in words
            if len(w) >= 3
            and w
            not in {
                "solace",
                "integration",
                "integrations",
                "micro",
                "producer",
                "consumer",
                "source",
                "target",
                "connector",
                "connect",
                "agent",
                "api",
                "managed",
                "apache",
                "amazon",
                "google",
                "microsoft",
                "azure",
                "cloud",
                "for",
                "with",
                "the",
                "and",
                "sap",
            }
        ]
        links = [
            {"title": n.text()[:180], "url": urljoin(entry["url"], n.attrs["href"])}
            for n in area.walk()
            if n.tag == "a" and n.attrs.get("href", "").startswith(("https://", "/"))
        ]
        entry.update(
            aliases=list(dict.fromkeys(aliases)),
            capabilities=summary,
            detail=area.text(),
            links=links,
            reviewedOn=downloaded[:10],
            downloadedAt=downloaded,
            htmlSha256=hashlib.sha256(raw).hexdigest(),
            reviewNotes=prior.get("reviewNotes", prior.get("capabilities", ""))
            if "detail" not in prior
            else prior.get("reviewNotes", ""),
        )
        print("Downloaded " + entry["name"], flush=True)
        return entry

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        full = list(pool.map(detail, entries))
    result = {
        "reviewedOn": downloaded[:10],
        "downloadedAt": downloaded,
        "hubUrl": HUB,
        "entryCount": total,
        "listingPages": pages,
        "coverage": f"Complete snapshot of all {total} unique results and their detail pages listed by Integration Hub at download time. Not an inventory of every possible third-party integration; availability and product requirements can change.",
        "indexSha256": hashlib.sha256(initial.encode()).hexdigest(),
        "entries": full,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Saved {len(full)} complete entries to {args.output}")


if __name__ == "__main__":
    main()
