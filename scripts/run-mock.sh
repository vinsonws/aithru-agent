#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_ROOT="${AITHRU_PLATFORM_ROOT:-"$ROOT_DIR/../aithru-platform"}"
BACKEND_PORT="${AITHRU_AGENT_BACKEND_PORT:-8000}"
FRONTEND_PORT="${AITHRU_AGENT_FRONTEND_PORT:-5173}"
MOCK_PORT="${AITHRU_MOCK_PORT:-19000}"
MOCK_URL="http://localhost:${MOCK_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"

mock_pid=""
backend_pid=""
frontend_pid=""

cleanup() {
  kill "$frontend_pid" "$backend_pid" "$mock_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

MOCK_HOST_DIR="$PLATFORM_ROOT/tools/platform-mock-host"

if [[ ! -f "$MOCK_HOST_DIR/package.json" ]]; then
  echo "Cannot find platform mock host at $MOCK_HOST_DIR" >&2
  exit 1
fi

(
  cd "$MOCK_HOST_DIR"
  if [[ ! -d node_modules ]]; then
    npm ci
  fi
  exec npx tsx src/cli.ts host --config "$ROOT_DIR/aithru.mock.yml" --port "$MOCK_PORT" --app-url "$FRONTEND_URL" --origin "$FRONTEND_URL"
) &
mock_pid=$!

(
  cd "$ROOT_DIR/backend"
  exec env \
    HOST=127.0.0.1 \
    PORT="$BACKEND_PORT" \
    AITHRU_PLATFORM_AUTH_ENABLED=true \
    AITHRU_PLATFORM_URL="$MOCK_URL" \
    AITHRU_ISSUER="$MOCK_URL" \
    AITHRU_APP_KEY=agent \
    AITHRU_CLIENT_SECRET=agent-mock-secret \
    AITHRU_PUBLIC_BASE_URL="$FRONTEND_URL" \
    AITHRU_API_BASE_URL="$FRONTEND_URL/api" \
    AITHRU_INTERNAL_BASE_URL="$BACKEND_URL/api" \
    AITHRU_HEALTH_URL="$BACKEND_URL/api/health" \
    AITHRU_FAIL_ON_REGISTRATION_ERROR=false \
    AITHRU_LIFECYCLE_ENABLED=false \
    AITHRU_HEARTBEAT_ENABLED=false \
    npm run dev
) &
backend_pid=$!

(
  cd "$ROOT_DIR/frontend"
  exec env \
    AITHRU_AGENT_BACKEND="$BACKEND_URL" \
    VITE_AITHRU_APP_KEY=agent \
    npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) &
frontend_pid=$!

echo "Open $MOCK_URL/apps/agent"
wait -n "$mock_pid" "$backend_pid" "$frontend_pid"
