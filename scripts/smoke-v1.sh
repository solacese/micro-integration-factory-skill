#!/usr/bin/env bash
# Verify generation, fresh installation, contracts, and a real local broker round trip.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MI_FACTORY_WORK="$(mktemp -d)"
export COMPOSE_PROJECT_NAME="mi-factory-smoke-$$"
export MI_HTTP_PORT="${MI_FACTORY_TEST_PORT:-18102}"
"${MI_FACTORY_PYTHON:-${ROOT}/apps/api/.venv/bin/python}" "${ROOT}/scripts/create-mi.py" \
  "${ROOT}/apps/api/resources/samples/core-java/uppercase.json" --output "${MI_FACTORY_WORK}"
cd "${MI_FACTORY_WORK}/uppercase-mi-v1"
cleanup() {
  local result=$?
  if [[ "$result" -ne 0 ]]; then
    docker compose -f compose.yaml -f compose.demo.yaml logs --no-color --tail=100 || true
  fi
  docker compose -f compose.yaml -f compose.demo.yaml down --volumes >/dev/null 2>&1 || true
  rm -rf "${MI_FACTORY_WORK}"
}
trap cleanup EXIT
./scripts/install.sh --demo
./scripts/smoke.sh --demo
curl --fail --silent "http://localhost:${MI_HTTP_PORT}/actuator/health"
echo 'Generated MI v1 passed fresh installation, contract tests, and a real broker round trip.'
