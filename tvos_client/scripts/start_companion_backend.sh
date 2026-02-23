#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/tvos_companion_backend"
VENV_DIR="${BACKEND_DIR}/.venv"
RUN_DIR="${BACKEND_DIR}/.run"
LOG_FILE="${RUN_DIR}/companion_backend.log"
PID_FILE="${RUN_DIR}/companion_backend.pid"
REQ_FILE="${BACKEND_DIR}/requirements.txt"
STAMP_FILE="${VENV_DIR}/.requirements.stamp"
ENV_FILE="${BACKEND_DIR}/.env.local"

CHECK_HOST="${COMPANION_CHECK_HOST:-127.0.0.1}"
HOST="${COMPANION_HOST:-0.0.0.0}"
PORT="${COMPANION_PORT:-8000}"
PROVIDER="${COMPANION_PROVIDER:-}"

if [ -z "${PROVIDER}" ] && [ -f "${ENV_FILE}" ]; then
  PROVIDER="$(sed -n 's/^COMPANION_PROVIDER=//p' "${ENV_FILE}" | head -n 1 | tr -d "\"'" | tr -d '[:space:]')"
fi
PROVIDER="${PROVIDER:-mock}"

log() {
  printf '[start-backend] %s\n' "$*"
}

backend_listening() {
  if command -v nc >/dev/null 2>&1; then
    nc -z "${CHECK_HOST}" "${PORT}" >/dev/null 2>&1
    return
  fi

  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi

  return 1
}

if [ ! -d "${BACKEND_DIR}" ]; then
  log "Backend directory not found: ${BACKEND_DIR}"
  exit 0
fi

if backend_listening; then
  log "Companion backend already listening on ${CHECK_HOST}:${PORT}"
  exit 0
fi

mkdir -p "${RUN_DIR}"

if [ -f "${PID_FILE}" ]; then
  rm -f "${PID_FILE}"
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    log "python3 not available, cannot start backend automatically"
    exit 0
  fi
  log "Creating backend virtual environment"
  if ! python3 -m venv "${VENV_DIR}" >> "${LOG_FILE}" 2>&1; then
    log "Failed creating virtual environment (see ${LOG_FILE})"
    exit 0
  fi
fi

if [ ! -f "${REQ_FILE}" ]; then
  log "requirements.txt missing at ${REQ_FILE}"
  exit 0
fi

if [ ! -f "${STAMP_FILE}" ] || [ "${REQ_FILE}" -nt "${STAMP_FILE}" ]; then
  log "Installing backend dependencies"
  if ! "${VENV_DIR}/bin/pip" install -r "${REQ_FILE}" >> "${LOG_FILE}" 2>&1; then
    log "Dependency install failed (see ${LOG_FILE})"
    exit 0
  fi
  touch "${STAMP_FILE}"
fi

log "Starting companion backend (${PROVIDER}) on ${HOST}:${PORT}"
(
  cd "${BACKEND_DIR}" || exit 1

  if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck source=/dev/null
    . "${ENV_FILE}"
    set +a
  fi

  COMPANION_PROVIDER="${COMPANION_PROVIDER:-${PROVIDER}}"
  nohup env COMPANION_PROVIDER="${COMPANION_PROVIDER}" "${VENV_DIR}/bin/python" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" >> "${LOG_FILE}" 2>&1 &
  echo $! > "${PID_FILE}"
)

sleep 1
if backend_listening; then
  log "Companion backend started successfully on ${CHECK_HOST}:${PORT}"
else
  log "Companion backend did not start (see ${LOG_FILE})"
fi

exit 0
