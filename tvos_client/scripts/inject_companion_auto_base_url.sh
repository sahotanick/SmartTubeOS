#!/usr/bin/env bash

set -u

PLIST_PATH="${1:-}"
PORT="${COMPANION_PORT:-8000}"
PLIST_BUDDY="/usr/libexec/PlistBuddy"

log() {
  printf '[auto-base-url] %s\n' "$*"
}

detect_lan_ipv4() {
  local iface ip

  iface="$(route -n get default 2>/dev/null | awk '/interface: / { print $2; exit }')"
  if [ -n "${iface}" ]; then
    ip="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"
    if [ -n "${ip}" ]; then
      printf '%s' "${ip}"
      return 0
    fi
  fi

  for iface in en0 en1 en2; do
    ip="$(ipconfig getifaddr "${iface}" 2>/dev/null || true)"
    if [ -n "${ip}" ]; then
      printf '%s' "${ip}"
      return 0
    fi
  done

  return 1
}

if [ -z "${PLIST_PATH}" ] || [ ! -f "${PLIST_PATH}" ]; then
  log "Info.plist not found at '${PLIST_PATH}', skipping"
  exit 0
fi

if [ ! -x "${PLIST_BUDDY}" ]; then
  log "PlistBuddy unavailable, skipping"
  exit 0
fi

LAN_IP="$(detect_lan_ipv4 || true)"
if [ -z "${LAN_IP}" ]; then
  log "Could not detect Mac LAN IPv4, keeping existing CompanionAutoBaseURL"
  exit 0
fi

AUTO_URL="http://${LAN_IP}:${PORT}"

if ! "${PLIST_BUDDY}" -c "Set :CompanionAutoBaseURL ${AUTO_URL}" "${PLIST_PATH}" >/dev/null 2>&1; then
  "${PLIST_BUDDY}" -c "Add :CompanionAutoBaseURL string ${AUTO_URL}" "${PLIST_PATH}" >/dev/null 2>&1 || true
fi

log "CompanionAutoBaseURL=${AUTO_URL}"
exit 0
