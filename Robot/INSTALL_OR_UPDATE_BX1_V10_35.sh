#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-/home/arduino/Arduino_Q_Client_V1}"
BACKUP_ROOT="${HOME}/bx1_backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/before_v10_35_${STAMP}"
BACKUP_ARCHIVE="${BACKUP_DIR}/project-before-v10_35.tgz"
BACKUP_PARTIAL="${BACKUP_ARCHIVE}.partial"
PYTHON_BIN=""
TARGET_EXISTED=0
BACKUP_READY=0
CHANGES_STARTED=0
BACKUP_PID=""
SERVICE_WAS_ACTIVE=0

say() { printf '\n[BX1 v10.35] %s\n' "$*"; }

finish_failure() {
  code="$1"
  trap - ERR INT TERM
  if [ -n "$BACKUP_PID" ]; then
    kill "$BACKUP_PID" >/dev/null 2>&1 || true
    wait "$BACKUP_PID" >/dev/null 2>&1 || true
  fi
  rm -f "$BACKUP_PARTIAL"
  printf '\n[BX1 v10.35] Installation failed (exit %s).\n' "$code" >&2
  if [ "$CHANGES_STARTED" -eq 1 ] && [ "$BACKUP_READY" -eq 1 ] && [ -d "$TARGET_DIR" ]; then
    printf '[BX1 v10.35] Restoring the previous program and configuration...\n' >&2
    tar -xzf "$BACKUP_ARCHIVE" -C "$TARGET_DIR" || true
  fi
  if [ "$SERVICE_WAS_ACTIVE" -eq 1 ] && command -v systemctl >/dev/null 2>&1; then
    sudo systemctl restart bx1-web.service >/dev/null 2>&1 || true
  fi
  printf '[BX1 v10.35] Backup: %s\n' "$BACKUP_DIR" >&2
  exit "$code"
}

restore_on_error() { finish_failure "$?"; }
stop_on_signal() { finish_failure 130; }
trap restore_on_error ERR
trap stop_on_signal INT TERM

if [ ! -f "${SOURCE_DIR}/python/main.py" ] || [ ! -f "${SOURCE_DIR}/tools/migrate_v10_35_config.py" ]; then
  printf '[BX1 v10.35] ERROR: run this script from the extracted Arduino_Q_Client_V10_35 folder.\n' >&2
  exit 2
fi

mkdir -p "$BACKUP_DIR"
if [ -d "$TARGET_DIR" ]; then
  TARGET_EXISTED=1
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet bx1-web.service; then
    SERVICE_WAS_ACTIVE=1
  fi
  say "Creating a fast rollback backup (program and configuration only)"
  printf '[BX1 v10.35] Skipping models, runtime audio, traces, old updates and archives.\n'
  (
    tar -cf - \
      --exclude='./.venv' \
      --exclude='./runtime' \
      --exclude='./models' \
      --exclude='./diagnostic_traces' \
      --exclude='./backups' \
      --exclude='./backup' \
      --exclude='./bx1_backups' \
      --exclude='./update_files' \
      --exclude='./files' \
      --exclude='./logs' \
      --exclude='./.git' \
      --exclude='*/__pycache__' \
      --exclude='*.zip' \
      --exclude='*.tgz' \
      --exclude='*.tar.gz' \
      --exclude='*.log' \
      -C "$TARGET_DIR" . | gzip -1 > "$BACKUP_PARTIAL"
  ) &
  BACKUP_PID=$!
  progress_tick=0
  while kill -0 "$BACKUP_PID" >/dev/null 2>&1; do
    sleep 1
    progress_tick=$((progress_tick + 1))
    if [ "$progress_tick" -ge 3 ] && kill -0 "$BACKUP_PID" >/dev/null 2>&1; then
      backup_size="$(du -h "$BACKUP_PARTIAL" 2>/dev/null | awk '{print $1}')"
      printf '[BX1 v10.35] Backup progress: %s written...\n' "${backup_size:-starting}"
      progress_tick=0
    fi
  done
  wait "$BACKUP_PID"
  BACKUP_PID=""
  gzip -t "$BACKUP_PARTIAL"
  tar -tzf "$BACKUP_PARTIAL" >/dev/null
  mv "$BACKUP_PARTIAL" "$BACKUP_ARCHIVE"
  BACKUP_READY=1
  backup_size="$(du -h "$BACKUP_ARCHIVE" | awk '{print $1}')"
  say "Rollback backup ready (${backup_size})"
fi

if [ "${BX1_BACKUP_ONLY:-0}" = "1" ]; then
  trap - ERR INT TERM
  say "Backup-only validation complete"
  printf 'Backup: %s\n' "$BACKUP_DIR"
  exit 0
fi

if command -v systemctl >/dev/null 2>&1; then
  say "Stopping the BX1 body service"
  sudo systemctl stop bx1-web.service >/dev/null 2>&1 || true
fi
CHANGES_STARTED=1

if [ "$(readlink -f "$SOURCE_DIR")" != "$(readlink -m "$TARGET_DIR")" ]; then
  say "Installing program files into $TARGET_DIR"
  mkdir -p "$TARGET_DIR"
  tar -cf - --exclude='./python/config.json' --exclude='./.venv' --exclude='./runtime' \
    --exclude='./models' --exclude='./__pycache__' -C "$SOURCE_DIR" . | tar -xf - -C "$TARGET_DIR"
else
  say "Program files are already in the target folder"
fi

if [ ! -f "${TARGET_DIR}/python/config.json" ]; then
  say "Creating a fresh body configuration"
  cp "${TARGET_DIR}/python/config.fresh.json" "${TARGET_DIR}/python/config.json"
fi

if [ -x "${TARGET_DIR}/.venv/bin/python" ]; then
  PYTHON_BIN="${TARGET_DIR}/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || true)"
fi
if [ -z "$PYTHON_BIN" ]; then
  printf '[BX1 v10.35] ERROR: python3 is not installed.\n' >&2
  exit 127
fi

if ! "$PYTHON_BIN" -c 'import requests, serial, msgpack' >/dev/null 2>&1; then
  say "Installing the small core Python dependencies"
  if [ ! -x "${TARGET_DIR}/.venv/bin/python" ]; then
    "$PYTHON_BIN" -m venv "${TARGET_DIR}/.venv"
    PYTHON_BIN="${TARGET_DIR}/.venv/bin/python"
  fi
  "$PYTHON_BIN" -m pip install --upgrade pip
  "$PYTHON_BIN" -m pip install -r "${TARGET_DIR}/python/requirements.txt"
fi

say "Migrating the saved settings without changing hardware calibration"
"$PYTHON_BIN" "${TARGET_DIR}/tools/migrate_v10_35_config.py" "${TARGET_DIR}/python/config.json"

say "Running offline release and syntax checks"
"$PYTHON_BIN" "${TARGET_DIR}/tools/test_v10_35.py" --project-root "$TARGET_DIR"
"$PYTHON_BIN" -m compileall -q "${TARGET_DIR}/python" "${TARGET_DIR}/tools"

chmod +x "${TARGET_DIR}/main.py" "${TARGET_DIR}/START_BX1_WEB.sh" "${TARGET_DIR}/STOP_BX1_WEB.sh" \
  "${TARGET_DIR}/INSTALL_OR_UPDATE_BX1_V10_35.sh" "${TARGET_DIR}/tools/"*.sh

say "Installing and starting the BX1 Linux service"
"${TARGET_DIR}/tools/install_bx1_web_service.sh"

trap - ERR INT TERM
say "Update complete"
printf 'Program: %s\n' "$TARGET_DIR"
printf 'Backup:  %s\n' "$BACKUP_DIR"
printf 'Web UI:  http://BX1-IP:8088\n'
printf 'MCU:     unchanged; no Arduino firmware flash was performed\n'
