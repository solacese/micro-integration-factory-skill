"""Lambda Function URL handler for the public, bounded MI v1 demo."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api/src"))
os.environ.setdefault("RUNS_ROOT", "/tmp/factory-runs")

from spec2event.services.advisor_service import AdvisorService  # noqa: E402

advisor = AdvisorService()


def _response(code, data):
    return {
        "statusCode": code,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(data),
    }


def _quota(event):
    """Atomic daily global budget plus per-IP minute budget; no raw IP retention."""
    table_name = os.getenv("QUOTA_TABLE")
    if not table_name:
        return
    import boto3
    from botocore.exceptions import ClientError

    table = boto3.resource("dynamodb").Table(table_name)
    now = int(time.time())
    ip = event.get("requestContext", {}).get("http", {}).get("sourceIp", "unknown")
    buckets = [
        (f"day:{now // 86400}", int(os.getenv("DAILY_BUILD_LIMIT", "200"))),
        (f"minute:{now // 60}:" + hashlib.sha256(ip.encode()).hexdigest()[:24], 6),
    ]
    for key, limit in buckets:
        try:
            table.update_item(
                Key={"bucket": key},
                UpdateExpression="ADD uses :one SET expiresAt=:expires",
                ConditionExpression="attribute_not_exists(uses) OR uses < :limit",
                ExpressionAttributeValues={
                    ":one": 1,
                    ":limit": limit,
                    ":expires": now + 172800,
                },
            )
        except ClientError as error:
            if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ValueError(
                    "The demo request limit has been reached. Try again later."
                ) from None
            raise


def lambda_handler(event, context):
    path = event.get("rawPath", "/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "OPTIONS":
        return _response(200, {})
    if path == "/health" and method == "GET":
        return _response(
            200,
            {
                "status": "ok",
                "provider": "SAP AI Core",
                "version": "core-v1",
                "revision": os.getenv("FACTORY_REVISION", "development"),
            },
        )
    if path != "/chat" or method != "POST":
        return _response(404, {"error": "Not found"})
    try:
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body, validate=True).decode()
        if len(body.encode()) > 100_000:
            return _response(413, {"error": "Request too large"})
        request = json.loads(body)
        if not isinstance(request, dict):
            raise ValueError("Send a JSON object")
        _quota(event)
        result = advisor.respond(request.get("messages"), request.get("coreJava", ""))
        return _response(200, result)
    except (ValueError, TypeError) as error:
        return _response(429 if "limit" in str(error) else 400, {"error": str(error)})
    except Exception as error:
        # Log only the class, never prompts, credential configuration or upstream bodies.
        print(json.dumps({"event": "build_failed", "errorType": type(error).__name__}))
        return _response(
            502,
            {
                "error": "The build service could not complete this request. Please retry."
            },
        )
