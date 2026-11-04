#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MI_FACTORY_WORK="$(mktemp -d)"
export COMPOSE_PROJECT_NAME="mi-factory-go-smoke-$$"
export MI_HTTP_PORT="${MI_FACTORY_TEST_PORT:-18104}"
"${MI_FACTORY_PYTHON:-${ROOT}/apps/api/.venv/bin/python}" "${ROOT}/scripts/create-mi.py" \
  "${MI_FACTORY_SPEC:-${ROOT}/apps/api/resources/samples/core-java/uppercase.json}" --both --go-transport "${MI_FACTORY_GO_TRANSPORT:-amqp}" --output "${MI_FACTORY_WORK}"
cd "${MI_FACTORY_WORK}"/*-go-mi-v1
cleanup() {
 local result=$?
 if [[ "$result" -ne 0 ]]; then docker compose -f compose.yaml -f compose.demo.yaml logs --no-color --tail=100 || true; fi
 docker compose -f compose.yaml -f compose.demo.yaml down --volumes >/dev/null 2>&1 || true
 rm -rf "${MI_FACTORY_WORK}"
}
trap cleanup EXIT
./scripts/install.sh --demo
./scripts/smoke.sh --demo
curl --fail --silent "http://localhost:${MI_HTTP_PORT}/actuator/health"
echo 'Generated Go MI passed fresh installation, contract tests, and real broker delivery.'
