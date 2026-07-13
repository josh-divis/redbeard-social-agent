#!/usr/bin/env bash
# Install systemd user or system service for the review dashboard.
# Default: system service (requires sudo) for always-on dashboard on the Pi.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_SRC="${PROJECT_ROOT}/systemd/redbeard-dashboard.service"
UNIT_NAME="redbeard-dashboard.service"

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "Missing $SERVICE_SRC"
  exit 1
fi

# Detect run user
RUN_USER="${SUDO_USER:-${USER}}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: create venv first in ${PROJECT_ROOT}"
  exit 1
fi

TMP_UNIT="$(mktemp)"
sed \
  -e "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  -e "s|__RUN_USER__|${RUN_USER}|g" \
  -e "s|__VENV_PY__|${VENV_PY}|g" \
  "$SERVICE_SRC" > "$TMP_UNIT"

echo "Installing ${UNIT_NAME} as user ${RUN_USER}"
echo "---"
cat "$TMP_UNIT"
echo "---"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo to install system service:"
  echo "  sudo $0"
  rm -f "$TMP_UNIT"
  exit 1
fi

install -m 644 "$TMP_UNIT" "/etc/systemd/system/${UNIT_NAME}"
rm -f "$TMP_UNIT"

systemctl daemon-reload
systemctl enable --now "${UNIT_NAME}"
systemctl status "${UNIT_NAME}" --no-pager || true

echo
echo "Dashboard should be up. Check:"
echo "  curl -s http://127.0.0.1:5050/health"
echo "  journalctl -u ${UNIT_NAME} -f"
