#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${BX1_ROOT:-/home/arduino/BX1}"
OLD_BODY="${BX1_OLD_BODY:-/home/arduino/Arduino_Q_Client_V1}"
OLD_MGMT="${BX1_OLD_MANAGEMENT:-/home/arduino/BX1_OS}"
echo "BX1 unified preflight (read-only)"
if command -v rsync >/dev/null 2>&1; then
  COPY_METHOD=rsync
elif command -v tar >/dev/null 2>&1; then
  COPY_METHOD='tar fallback'
else
  echo 'BLOCKED: no supported copy method available (rsync or tar)' >&2
  exit 2
fi
echo "Copy method: $COPY_METHOD"
for path in "$OLD_BODY" "$OLD_MGMT" "$OLD_BODY/.venv/bin/python" "$OLD_MGMT/.venv/bin/python"; do
  [[ -e "$path" ]] || { echo "BLOCKED missing: $path"; exit 2; }
  echo "OK $path"
done
echo "-- services --"; systemctl is-enabled bx1-web.service bx1-os-alpha.service bx1-touchscreen.service bx1-kiosk.service 2>&1 || true
echo "-- listeners/processes --"; ss -ltnp | grep -E ':8088|:8089' || true
ps -eo pid,ppid,user,args | grep -E 'main.py|bx1_management|run_bx1|touchscreen' | grep -v grep || true
echo "-- body entrypoint --"; systemctl show -p ExecStart bx1-web.service 2>/dev/null || true
echo "-- management entrypoint --"; systemctl show -p ExecStart bx1-os-alpha.service 2>/dev/null || true
echo "-- writable data --"
for d in "$OLD_BODY/runtime" "$OLD_BODY/logs" "$OLD_BODY/diagnostic_traces" "$OLD_BODY/models" "$OLD_MGMT/runtime" "$OLD_MGMT/logs" "$OLD_MGMT/cache"; do
  [[ -e "$d" ]] && du -sh "$d"
done
echo "-- virtual environments --"
for v in "$OLD_BODY/.venv" "$OLD_MGMT/.venv"; do
  cat "$v/pyvenv.cfg"
  grep -RIl '^#!.*\(/home/arduino/Arduino_Q_Client_V1\|/home/arduino/BX1_OS\)' "$v/bin" 2>/dev/null | head -20 || true
done
echo "Preflight complete; no changes made."
