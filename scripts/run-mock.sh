#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLATFORM_ROOT="${AITHRU_PLATFORM_ROOT:-"$ROOT_DIR/../aithru-platform"}"
DEFAULT_BACKEND_PORT=8000
DEFAULT_FRONTEND_PORT=5173
DEFAULT_MOCK_PORT=19000

port_in_use() {
  local port="$1"

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  fi

  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1 && return 0
    nc -z localhost "$port" >/dev/null 2>&1 && return 0
  fi

  return 1
}

pick_port() {
  local label="$1"
  local default_port="$2"
  local port="$default_port"

  while port_in_use "$port"; do
    port=$((port + 1))
  done

  if [[ "$port" != "$default_port" ]]; then
    echo "${label} port ${default_port} is in use; using ${port}." >&2
  fi

  printf '%s\n' "$port"
}

port_from_env_or_free() {
  local env_name="$1"
  local label="$2"
  local default_port="$3"
  local value="${!env_name:-}"

  if [[ -n "$value" ]]; then
    printf '%s\n' "$value"
  else
    pick_port "$label" "$default_port"
  fi
}

BACKEND_PORT="$(port_from_env_or_free AITHRU_AGENT_BACKEND_PORT Backend "$DEFAULT_BACKEND_PORT")"
FRONTEND_PORT="$(port_from_env_or_free AITHRU_AGENT_FRONTEND_PORT Frontend "$DEFAULT_FRONTEND_PORT")"
MOCK_PORT="$(port_from_env_or_free AITHRU_MOCK_PORT Mock "$DEFAULT_MOCK_PORT")"
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

wait_for_any() {
  while :; do
    local running
    running="$(jobs -pr)"
    for pid in "$@"; do
      if ! printf '%s\n' "$running" | grep -qx "$pid"; then
        wait "$pid"
        return $?
      fi
    done
    sleep 1
  done
}

ensure_npm_deps() {
  local dir="$1"
  local lock="$dir/package-lock.json"
  local installed_lock="$dir/node_modules/.package-lock.json"

  if [[ -d "$dir/node_modules" && ( ! -f "$lock" || ( -f "$installed_lock" && ! "$lock" -nt "$installed_lock" ) ) ]]; then
    return
  fi

  (
    cd "$dir"
    if [[ -f package-lock.json ]]; then
      npm ci
    else
      npm install
    fi
  )
}

MOCK_HOST_DIR="$PLATFORM_ROOT/tools/platform-mock-host"

if [[ ! -f "$MOCK_HOST_DIR/package.json" ]]; then
  echo "Cannot find platform mock host at $MOCK_HOST_DIR" >&2
  exit 1
fi

(
  cd "$MOCK_HOST_DIR"
  ensure_npm_deps "$MOCK_HOST_DIR"
  exec npx tsx src/cli.ts host --config "$ROOT_DIR/aithru.mock.yml" --port "$MOCK_PORT" --publicUrl "$MOCK_URL" --issuer "$MOCK_URL" --app-url "$FRONTEND_URL" --origin "$FRONTEND_URL"
) &
mock_pid=$!

(
  cd "$ROOT_DIR/backend"
  ensure_npm_deps "$ROOT_DIR/backend"
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
  ensure_npm_deps "$ROOT_DIR/frontend"
  exec env \
    AITHRU_AGENT_BACKEND="$BACKEND_URL" \
    VITE_AITHRU_APP_KEY=agent \
    npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) &
frontend_pid=$!

echo "Open $MOCK_URL/apps/agent"
wait_for_any "$mock_pid" "$backend_pid" "$frontend_pid"
