#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKEND_ADDR="${AITHRU_AGENT_BACKEND_ADDR:-127.0.0.1:8000}"
BACKEND_HOST="${AITHRU_AGENT_BACKEND_HOST:-${BACKEND_ADDR%:*}}"
BACKEND_PORT="${AITHRU_AGENT_BACKEND_PORT:-${BACKEND_ADDR##*:}}"
BACKEND_URL="${AITHRU_AGENT_BACKEND_URL:-http://${BACKEND_HOST}:${BACKEND_PORT}}"

FRONTEND_HOST="${AITHRU_AGENT_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${AITHRU_AGENT_FRONTEND_PORT:-5173}"

WORKER_POLL_INTERVAL="${AITHRU_AGENT_WORKER_POLL_INTERVAL:-1}"
SQLITE_PATH="${AITHRU_AGENT_SQLITE_PATH:-${ROOT_DIR}/backend/.aithru/agent.sqlite}"

backend_pid=""
worker_pid=""
frontend_pid=""

require_command() {
  local name="$1"

  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name" >&2
    exit 127
  fi
}

require_port_available() {
  local host="$1"
  local port="$2"
  local label="$3"

  if command -v lsof >/dev/null 2>&1; then
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR > 1 { found = 1 } END { exit !found }'; then
      echo "${label} port is already in use: ${host}:${port}" >&2
      echo "Stop the existing server or override the port with an AITHRU_AGENT_* env var." >&2
      exit 98
    fi
  fi
}

terminate_process_tree() {
  local pid="${1:-}"
  local child_pid

  if [[ -z "$pid" ]]; then
    return 0
  fi

  if command -v pgrep >/dev/null 2>&1; then
    while IFS= read -r child_pid; do
      terminate_process_tree "$child_pid"
    done < <(pgrep -P "$pid" 2>/dev/null || true)
  fi

  kill "$pid" 2>/dev/null || true
}

terminate_process_group() {
  local pid="${1:-}"

  if [[ -z "$pid" ]]; then
    return 0
  fi

  terminate_process_tree "$pid"
}

cleanup() {
  local status="${1:-$?}"

  trap - EXIT INT TERM
  {
    terminate_process_group "$frontend_pid"
    terminate_process_group "$worker_pid"
    terminate_process_group "$backend_pid"
    wait "$frontend_pid" "$worker_pid" "$backend_pid" || true
  } 2>/dev/null
  exit "$status"
}

finish_when_child_exits() {
  local pid="$1"
  local status

  set +e
  wait "$pid"
  status=$?
  set -e
  exit "$status"
}

trap cleanup EXIT
trap 'cleanup 130' INT
trap 'cleanup 143' TERM

require_command uv
require_command npm

require_port_available "$BACKEND_HOST" "$BACKEND_PORT" "Backend"
require_port_available "$FRONTEND_HOST" "$FRONTEND_PORT" "Frontend"

mkdir -p "$(dirname "$SQLITE_PATH")"

export AITHRU_AGENT_MODEL="${AITHRU_AGENT_MODEL:-test}"
export AITHRU_AGENT_PERSISTENCE_BACKEND="${AITHRU_AGENT_PERSISTENCE_BACKEND:-sqlite}"
export AITHRU_AGENT_SQLITE_PATH="$SQLITE_PATH"
export AITHRU_AGENT_BACKEND="$BACKEND_URL"

echo "Starting Aithru Agent backend: ${BACKEND_URL}"
(
  cd "$ROOT_DIR/backend"
  exec uv run uvicorn aithru_agent.api.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload
) &
backend_pid=$!

echo "Starting Aithru Agent worker: sqlite://${SQLITE_PATH}"
(
  cd "$ROOT_DIR/backend"
  exec uv run aithru-agent-worker --loop --poll-interval "$WORKER_POLL_INTERVAL" --sqlite-path "$SQLITE_PATH"
) &
worker_pid=$!

echo "Starting Aithru Agent frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
(
  cd "$ROOT_DIR/frontend"
  exec npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort
) &
frontend_pid=$!

echo "Press Ctrl-C to stop backend, worker, and frontend."

while true; do
  if ! jobs -pr | grep -qx "$backend_pid"; then
    finish_when_child_exits "$backend_pid"
  fi

  if ! jobs -pr | grep -qx "$worker_pid"; then
    finish_when_child_exits "$worker_pid"
  fi

  if ! jobs -pr | grep -qx "$frontend_pid"; then
    finish_when_child_exits "$frontend_pid"
  fi

  sleep 1
done
