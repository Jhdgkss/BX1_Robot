#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${BX1_ROOT:-/home/arduino/BX1}"
fail=0
[[ -L "$ROOT/current" && -d "$ROOT/current/body" && -d "$ROOT/current/management" ]] || { echo 'current release missing'; fail=1; }
systemctl is-active --quiet bx1-body.service || { echo 'bx1-body.service inactive'; fail=1; }
systemctl is-active --quiet bx1-management.service || { echo 'bx1-management.service inactive'; fail=1; }
if systemctl is-enabled --quiet bx1-touchscreen.service 2>/dev/null; then systemctl is-active --quiet bx1-touchscreen.service || { echo 'bx1-touchscreen.service inactive'; fail=1; }; fi
[[ "$(ss -ltn | grep -c ':8088 ')" -eq 1 ]] || { echo 'port 8088 ownership invalid'; fail=1; }
[[ "$(ss -ltn | grep -c ':8089 ')" -eq 1 ]] || { echo 'port 8089 ownership invalid'; fail=1; }
curl --fail --silent --max-time 5 http://127.0.0.1:8088/api/status >/dev/null || { echo 'Body health failed'; fail=1; }
curl --fail --silent --max-time 5 http://127.0.0.1:8089/api/status >/dev/null || { echo 'Management health failed'; fail=1; }
if journalctl -u bx1-body.service -u bx1-management.service -b --since '-90 seconds' --no-pager | grep -Eiq 'traceback|syntaxerror|fatal exception'; then echo 'startup traceback detected'; fail=1; fi
[[ $fail -eq 0 ]] || exit 1
echo "Unified BX1 validation passed: $(readlink -f "$ROOT/current")"
