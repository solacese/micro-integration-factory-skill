from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import boto3
import httpx
import psycopg


def load_env_file(path: Path) -> None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ[key] = value


def check_aws() -> dict[str, Any]:
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        region_name=os.getenv("AWS_REGION", "ca-central-1"),
    )
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    return {
        "ok": True,
        "account": identity.get("Account"),
        "arn": identity.get("Arn"),
    }


def check_database() -> dict[str, Any]:
    database_url = os.getenv("SOURCE_DATABASE_URL")
    if not database_url:
        return {"ok": True, "skipped": True, "reason": "SOURCE_DATABASE_URL not set"}
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select table_schema, table_name
                from information_schema.tables
                where table_schema not in ('pg_catalog', 'information_schema')
                order by table_schema, table_name
                limit 10
                """
            )
            tables = [f"{schema}.{table}" for schema, table in cur.fetchall()]
    return {"ok": True, "tables": tables}


def _event_portal_api_base(raw: str) -> str:
    base = raw.rstrip("/")
    if base.endswith("/ep/designer"):
        return "https://api.solace.cloud/api/v2/architecture"
    if "/api/" in base:
        return base
    return base


def check_event_portal() -> dict[str, Any]:
    base_url = os.getenv("EVENT_PORTAL_BASE_URL")
    token = os.getenv("EVENT_PORTAL_TOKEN")
    if not base_url or not token:
        return {"ok": True, "skipped": True, "reason": "Event Portal credentials not set"}
    api_base = _event_portal_api_base(base_url)
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(
            f"{api_base}/applicationDomains?pageSize=1",
            headers={"Authorization": f"Bearer {token}"},
        )
    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "body_preview": response.text[:300],
    }


def check_litellm() -> dict[str, Any]:
    base_url = os.getenv("LITELLM_BASE_URL")
    api_key = os.getenv("LITELLM_API_KEY")
    if not base_url or not api_key:
        return {"ok": True, "skipped": True, "reason": "LiteLLM credentials not set"}
    with httpx.Client(timeout=20.0) as client:
        response = client.get(
            f"{base_url.rstrip('/')}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    return {
        "ok": response.is_success,
        "status_code": response.status_code,
        "body_preview": response.text[:300],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the main demo integrations before a run.")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()

    env_path = Path(args.env_file).resolve()
    if not env_path.exists():
        raise SystemExit(f"Missing env file: {env_path}")

    load_env_file(env_path)

    report = {
        "envFile": str(env_path),
        "checks": {
            "aws": _safe(check_aws),
            "database": _safe(check_database),
            "eventPortal": _safe(check_event_portal),
            "litellm": _safe(check_litellm),
        },
    }
    print(json.dumps(report, indent=2))


def _safe(fn: Any) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__, "message": str(exc)}


if __name__ == "__main__":
    main()
