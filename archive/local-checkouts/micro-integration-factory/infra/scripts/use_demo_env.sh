#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

mode="${1:-}"

case "$mode" in
  openapi)
    source_file="$REPO_ROOT/infra/demo/env/openapi.env"
    prompt_file="$REPO_ROOT/infra/demo/prompts/openapi_ec2_event_portal.md"
    ;;
  postgres)
    source_file="$REPO_ROOT/infra/demo/env/postgres.env"
    prompt_file="$REPO_ROOT/infra/demo/prompts/postgres_ec2_event_portal.md"
    ;;
  hybrid)
    source_file="$REPO_ROOT/infra/demo/env/hybrid.env"
    prompt_file="$REPO_ROOT/infra/demo/prompts/openapi_postgres_ec2_event_portal.md"
    ;;
  *)
    echo "Usage: $0 {openapi|postgres|hybrid}" >&2
    exit 1
    ;;
esac

cp "$source_file" "$REPO_ROOT/.env.active"
cp "$source_file" "$REPO_ROOT/.env"
echo "Activated demo env from $source_file"
echo "Suggested prompt: $prompt_file"
