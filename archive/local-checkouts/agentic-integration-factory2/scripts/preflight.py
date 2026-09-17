from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

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


def check_ecr() -> dict[str, Any]:
    repository_name = os.getenv("ECR_REPOSITORY_NAME")
    if not repository_name:
        return {"ok": True, "skipped": True, "reason": "ECR_REPOSITORY_NAME not set"}
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        region_name=os.getenv("AWS_REGION", "ca-central-1"),
    )
    ecr = session.client("ecr")
    response = ecr.describe_repositories(repositoryNames=[repository_name])
    repository = response["repositories"][0]
    return {
        "ok": True,
        "repository": repository["repositoryName"],
        "repositoryUri": repository["repositoryUri"],
    }


def _database_url() -> str | None:
    database_url = os.getenv("SOURCE_DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("SOURCE_DATABASE_HOST")
    port = os.getenv("SOURCE_DATABASE_PORT", "5432")
    database_name = os.getenv("SOURCE_DATABASE_NAME")
    username = os.getenv("SOURCE_DATABASE_USERNAME")
    password = os.getenv("SOURCE_DATABASE_PASSWORD")
    sslmode = os.getenv("SOURCE_DATABASE_SSLMODE", "require")
    if not all([host, database_name, username]) or password in (None, ""):
        return None
    return (
        f"postgresql://{quote(username)}:{quote(password)}@{host}:{port}/{database_name}"
        f"?sslmode={quote(sslmode)}"
    )


def check_database() -> dict[str, Any]:
    database_url = _database_url()
    if not database_url:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Database source credentials not fully set",
        }
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            schema = os.getenv("SOURCE_DATABASE_SCHEMA", "public")
            cur.execute(
                """
                select table_schema, table_name
                from information_schema.tables
                where table_schema = %s
                order by table_schema, table_name
                limit 10
                """,
                (schema,),
            )
            tables = [f"{schema}.{table}" for schema, table in cur.fetchall()]
            preferred_table = os.getenv("SOURCE_DATABASE_PREFERRED_TABLE", "products")
            cur.execute(
                """
                select 1
                from information_schema.tables
                where table_schema = %s and table_name = %s
                """,
                (schema, preferred_table),
            )
            preferred_present = cur.fetchone() is not None
    return {
        "ok": True,
        "tables": tables,
        "preferredTable": preferred_table,
        "preferredTablePresent": preferred_present,
    }


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
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(
                f"{api_base}/applicationDomains?pageSize=1",
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        message = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in message:
            return {
                "ok": False,
                "error": "TLSVerificationError",
                "message": message,
                "hint": (
                    "The local trust store cannot verify the Event Portal TLS chain. "
                    "Fix local CA trust rather than disabling verification."
                ),
            }
        raise
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


def check_paths() -> dict[str, Any]:
    paths = {
        "workspaceRoot": Path(os.getenv("WORKSPACE_ROOT") or ""),
        "runsRoot": Path(os.getenv("RUNS_ROOT") or ""),
        "mdkSampleRoot": Path(os.getenv("MDK_SAMPLE_ROOT") or ""),
    }
    results = {
        name: {"path": str(path), "exists": path.exists()}
        for name, path in paths.items()
        if str(path)
    }
    return {
        "ok": all(item["exists"] for item in results.values()),
        "paths": results,
    }


def check_ec2_prereqs() -> dict[str, Any]:
    deployment_target = os.getenv("DEPLOYMENT_TARGET", "ec2")
    if deployment_target not in {"ec2", "ephemeral_ec2"}:
        return {
            "ok": True,
            "skipped": True,
            "reason": f"Deployment target {deployment_target} does not use the EC2 demo path",
        }

    if os.getenv("DEPLOY_EC2_HOST"):
        missing: list[str] = []
        if not os.getenv("DEPLOY_EC2_SSH_USER"):
            missing.append("DEPLOY_EC2_SSH_USER")
        return {
            "ok": not missing,
            "mode": "direct_host",
            "missing": missing,
        }

    missing = [
        name
        for name in ("CONTROL_PLANE_SUBNET_ID", "CONTROL_PLANE_VPC_ID", "PUBLIC_BASE_URL")
        if not os.getenv(name)
    ]
    return {
        "ok": not missing,
        "mode": "ephemeral_ec2",
        "missing": missing,
        "note": (
            "CONTROL_PLANE_SECURITY_GROUP_ID is optional because the control plane can create "
            "one when VPC and subnet are set."
        ),
    }


def check_openapi_source() -> dict[str, Any]:
    source_mode = os.getenv("SOURCE_MODE", "openapi")
    multi_modes = {
        item.strip()
        for item in os.getenv("SOURCE_MULTI_MODES", "").split(",")
        if item.strip()
    }
    needs_openapi = source_mode == "openapi" or "openapi" in multi_modes
    if not needs_openapi:
        return {"ok": True, "skipped": True, "reason": "OpenAPI source not active"}
    source_file = os.getenv("SOURCE_OPENAPI_FILE")
    if not source_file:
        return {"ok": False, "message": "SOURCE_OPENAPI_FILE is required for the OpenAPI path"}
    path = Path(source_file)
    return {"ok": path.exists(), "path": str(path), "exists": path.exists()}


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
            "ecr": _safe(check_ecr),
            "database": _safe(check_database),
            "paths": _safe(check_paths),
            "ec2Prereqs": _safe(check_ec2_prereqs),
            "openapiSource": _safe(check_openapi_source),
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
