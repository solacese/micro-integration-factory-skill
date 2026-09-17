#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-${ROOT_DIR}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
else
  echo "No ${ENV_FILE}; using current environment and the AWS credential chain."
fi

: "${PUBLIC_BASE_URL:=http://mi.sol-se-emea.com}"
: "${AWS_REGION:=ca-central-1}"
: "${AWS_SDK_LOAD_CONFIG:=1}"
: "${AWS_ROLE_SESSION_NAME:=micro-integration-factory-deploy}"
: "${AUTO_AWS_SSO_LOGIN:=true}"
: "${CONTROL_PLANE_ALLOWED_CIDR:=0.0.0.0/0}"
export PUBLIC_BASE_URL AWS_REGION AWS_SDK_LOAD_CONFIG AWS_ROLE_SESSION_NAME CONTROL_PLANE_ALLOWED_CIDR

profile_uses_sso() {
  local profile_name="$1"
  local sso_start_url=""
  local sso_session=""
  sso_start_url="$(aws configure get sso_start_url --profile "${profile_name}" 2>/dev/null || true)"
  sso_session="$(aws configure get sso_session --profile "${profile_name}" 2>/dev/null || true)"
  [[ -n "${sso_start_url}" || -n "${sso_session}" ]]
}

aws_identity_args=()
if [[ -n "${AWS_PROFILE:-}" ]]; then
  aws_identity_args+=(--profile "${AWS_PROFILE}")
fi

aws_get_caller_identity() {
  if (( ${#aws_identity_args[@]} > 0 )); then
    aws sts get-caller-identity "${aws_identity_args[@]}"
  else
    aws sts get-caller-identity
  fi
}

if command -v aws >/dev/null 2>&1; then
  if ! aws_get_caller_identity >/dev/null 2>&1; then
    if [[ -n "${AWS_PROFILE:-}" && "${AUTO_AWS_SSO_LOGIN}" == "true" ]] && profile_uses_sso "${AWS_PROFILE}"; then
      echo "AWS profile ${AWS_PROFILE} is not currently authenticated; running aws sso login."
      aws sso login --profile "${AWS_PROFILE}"
    fi
    if ! aws_get_caller_identity >/dev/null 2>&1; then
      echo "AWS credentials are not available."
      echo "Use AWS_PROFILE with SSO/credential_process, AWS_ROLE_ARN, an instance role, or pasted STS values."
      exit 1
    fi
  fi
else
  echo "AWS CLI not found; boto3 will use AWS_PROFILE, credential_process, env vars, or instance role."
fi

echo "Deploying Micro Integration Factory to ${PUBLIC_BASE_URL}"
cd "${ROOT_DIR}/apps/api"
PYTHONPATH=src uv run python -m spec2event.control_plane deploy
