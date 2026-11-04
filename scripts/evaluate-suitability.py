#!/usr/bin/env python3
"""Replay all 111 catalog recommendations and natural-language fit cases through real AI Core.

Explicit --ai-core-env is required; credentials stay in process memory. No code is generated,
no cloud validation jobs are submitted, and no source systems receive test traffic.
"""

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))
from dotenv import dotenv_values  # noqa: E402
from spec2event.adapters.ai.sap_ai_core import SapAiCoreProvider  # noqa: E402
from spec2event.services.suitability_service import (  # noqa: E402
    CATALOG,
    SuitabilityService,
    match_score,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ai-core-env", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--natural-only", action="store_true")
    parser.add_argument(
        "--case", action="append", help="Replay only the named case ID; may be repeated"
    )
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    credentials = {
        k: v
        for k, v in dotenv_values(args.ai_core_env).items()
        if v and (k.startswith("SAP_") or k.startswith("AI_CORE_"))
    }
    saved = json.loads(CATALOG.read_text())
    cases = json.loads((ROOT / "apps/api/resources/evals/suitability.json").read_text())
    if not args.natural_only:
        cases = [
            {
                "id": "catalog/" + e["id"],
                "request": "I need the capability advertised by the '"
                + e["name"]
                + "' entry in Solace Integration Hub. Should I build a separate custom MI, or use that existing asset?",
                "decisions": ["reuse", "clarify"]
                if e["assetType"] == "Integration Guides"
                else ["reuse"],
                "matches": [e["id"]],
            }
            for e in saved["entries"]
        ] + cases
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]
        if len(cases) != len(wanted):
            parser.error("Unknown evaluation case")

    def catalog_lookup(request):
        entries = [dict(e, verification="snapshot") for e in saved["entries"]]
        top = sorted(entries, key=lambda e: match_score(request, e), reverse=True)[:5]
        return {
            "url": saved["hubUrl"],
            "checkedAt": datetime.now(UTC).isoformat(),
            "indexStatus": "snapshot_replay",
            "reviewedOn": saved["reviewedOn"],
            "coverage": saved["coverage"],
            "entryCount": saved["entryCount"],
            "downloadedAt": saved["downloadedAt"],
            "indexSha256": saved["indexSha256"],
            "entries": entries,
            "highlightedIds": [e["id"] for e in top],
            "sources": [],
        }

    def evaluate(case):
        started = time.monotonic()
        try:
            # Separate provider/client per request; no shared OAuth mutation.
            result = SuitabilityService(
                SapAiCoreProvider(credentials), catalog_lookup
            ).assess(case["request"])
            selected = {m["id"] for m in result["matches"]}
            covering = {
                m["id"] for m in result["matches"] if m["fit"] == "covers_request"
            }
            passed = (
                result["decision"] in case["decisions"]
                and (not case.get("matches") or bool(selected & set(case["matches"])))
                and not bool(covering & set(case.get("forbidCovering", [])))
            )
            record = {
                **case,
                "passed": passed,
                "actualDecision": result["decision"],
                "actualMatches": list(selected),
                "assessment": result,
                "seconds": round(time.monotonic() - started, 2),
            }
        except Exception as error:
            record = {
                **case,
                "passed": False,
                "error": str(error),
                "seconds": round(time.monotonic() - started, 2),
            }
        print(
            ("PASS " if record["passed"] else "FAIL ")
            + case["id"]
            + " "
            + record.get("actualDecision", record.get("error", "")),
            flush=True,
        )
        return record

    results = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(evaluate, case) for case in cases]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            report = {
                "testedAt": datetime.now(UTC).isoformat(),
                "catalogEntryCount": saved["entryCount"],
                "catalogIndexSha256": saved["indexSha256"],
                "mode": "real AI Core, complete downloaded catalog; no generation or live source traffic",
                "total": len(cases),
                "completed": len(results),
                "passed": sum(r["passed"] for r in results),
                "results": results,
            }
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    passed = sum(r["passed"] for r in results)
    print(f"Result: {passed}/{len(cases)} passed", flush=True)
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    main()
