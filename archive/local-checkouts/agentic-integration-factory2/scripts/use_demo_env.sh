#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

mode="${1:-}"

case "$mode" in
  openapi)
    source_file="$REPO_ROOT/demo/env/openapi.env"
    prompt_file="$REPO_ROOT/demo/prompts/openapi_ec2_event_portal.md"
    ;;
  postgres)
    source_file="$REPO_ROOT/demo/env/postgres.env"
    prompt_file="$REPO_ROOT/demo/prompts/postgres_ec2_event_portal.md"
    ;;
  hybrid)
    source_file="$REPO_ROOT/demo/env/hybrid.env"
    prompt_file="$REPO_ROOT/demo/prompts/openapi_postgres_ec2_event_portal.md"
    ;;
  *)
    echo "Usage: $0 {openapi|postgres|hybrid}" >&2
    exit 1
    ;;
esac

tmp_file="$(mktemp)"

python3 - "$source_file" "$REPO_ROOT" "$tmp_file" "$REPO_ROOT/.env" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path


source_file = Path(sys.argv[1])
repo_root = sys.argv[2]
target_file = Path(sys.argv[3])
current_env = Path(sys.argv[4])

preserve_keys = {
    "APP_ENCRYPTION_KEY",
    "DEMO_ADMIN_PASSWORD",
    "DATABASE_URL",
    "REDIS_URL",
    "ALLOW_INSECURE_LOCAL_LOGIN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "CONTROL_PLANE_SECURITY_GROUP_ID",
    "CONTROL_PLANE_SUBNET_ID",
    "CONTROL_PLANE_VPC_ID",
    "PUBLIC_BASE_URL",
    "DEPLOY_EC2_HOST",
    "DEPLOY_EC2_SSH_USER",
    "DEPLOY_EC2_SSH_PRIVATE_KEY",
    "DEPLOY_EC2_PORT",
    "K8S_API_SERVER",
    "K8S_TOKEN",
    "K8S_NAMESPACE",
    "K8S_CA_CERT",
    "RANCHER_URL",
    "RANCHER_TOKEN",
    "CONTAINER_REGISTRY",
    "CONTAINER_REGISTRY_USERNAME",
    "CONTAINER_REGISTRY_PASSWORD",
    "CONTAINER_IMAGE_PREFIX",
    "SOLACE_BROKER_URL",
    "SOLACE_VPN",
    "SOLACE_USERNAME",
    "SOLACE_PASSWORD",
    "SOLACE_WEB_MESSAGING_URL",
    "EVENT_PORTAL_BASE_URL",
    "EVENT_PORTAL_TOKEN",
    "EVENT_PORTAL_ORG_ID",
    "EVENT_PORTAL_DOMAIN_ID",
    "EVENT_PORTAL_RUNTIME_REGION",
    "SERDES_REGISTRY_URL",
    "SERDES_REGISTRY_TYPE",
    "SERDES_REGISTRY_API_KEY",
    "SERDES_REGISTRY_USERNAME",
    "SERDES_REGISTRY_PASSWORD",
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LITELLM_MODEL",
    "SOURCE_DATABASE_URL",
    "SOURCE_DATABASE_HOST",
    "SOURCE_DATABASE_PORT",
    "SOURCE_DATABASE_NAME",
    "SOURCE_DATABASE_SCHEMA",
    "SOURCE_DATABASE_USERNAME",
    "SOURCE_DATABASE_PASSWORD",
    "SOURCE_DATABASE_SSLMODE",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
}


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        result[key] = value
    return result


lines = source_file.read_text(encoding="utf-8").replace("__REPO_ROOT__", repo_root).splitlines()
current = parse_env(current_env)
template = {
    key: value.replace("__REPO_ROOT__", repo_root)
    for key, value in parse_env(source_file).items()
}

for key in preserve_keys:
    value = current.get(key)
    if value in (None, ""):
        continue
    template[key] = value

rendered: list[str] = []
seen: set[str] = set()
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        rendered.append(line.replace("__REPO_ROOT__", repo_root))
        continue
    key, _ = line.split("=", 1)
    rendered.append(f"{key}={template.get(key, '')}")
    seen.add(key)

for key in sorted(preserve_keys - seen):
    value = template.get(key)
    if value not in (None, ""):
        rendered.append(f"{key}={value}")

target_file.write_text("\n".join(rendered) + "\n", encoding="utf-8")
PY

cp "$tmp_file" "$REPO_ROOT/.env.active"
cp "$tmp_file" "$REPO_ROOT/.env"
rm -f "$tmp_file"
echo "Activated demo env from $source_file"
echo "Suggested prompt: $prompt_file"
