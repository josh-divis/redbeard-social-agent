#!/usr/bin/env bash
# Install cron jobs for RedBeard Social Agent on Raspberry Pi OS.
# Generates batches Mon & Thu at 08:00 America/Phoenix (set system TZ or use CRON_TZ).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
LOG_DIR="${PROJECT_ROOT}/data/logs"
MARKER="# redbeard-social-agent"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv not found at $VENV_PY"
  echo "Create it first: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

mkdir -p "$LOG_DIR"

# Use CRON_TZ so schedule is Phoenix time even if system is UTC
CRON_BLOCK=$(cat <<EOF
${MARKER}
CRON_TZ=America/Phoenix
# Generate review batches twice per week (Mon, Thu 08:00)
0 8 * * 1,4 cd ${PROJECT_ROOT} && ${VENV_PY} -m agent.cli generate >> ${LOG_DIR}/cron-generate.log 2>&1
# Optional Monday morning status snapshot
5 8 * * 1 cd ${PROJECT_ROOT} && ${VENV_PY} -m agent.cli status >> ${LOG_DIR}/cron-status.log 2>&1
EOF
)

# Remove old block if present, then append
EXISTING="$(crontab -l 2>/dev/null || true)"
FILTERED="$(printf '%s\n' "$EXISTING" | sed "/${MARKER}/,/^$/d" || true)"

{
  printf '%s\n' "$FILTERED"
  printf '%s\n' "$CRON_BLOCK"
  echo
} | crontab -

echo "Cron installed:"
crontab -l | sed -n "/${MARKER}/,/^$/p"
echo
echo "Logs: ${LOG_DIR}/cron-generate.log"
echo "Done. Edit schedule with: crontab -e"
