#!/usr/bin/env bash
set -Eeuo pipefail
BACKUP="${1:?usage: rollback_bx1_legacy_layout.sh /home/arduino/BX1/backups/pre-unified-<timestamp>}"
OLD_BODY="/home/arduino/Arduino_Q_Client_V1"; OLD_MGMT="/home/arduino/BX1_OS"
[[ -d "$BACKUP/body" && -d "$BACKUP/management" ]] || { echo 'invalid pre-unification backup' >&2; exit 2; }
systemctl stop bx1-touchscreen.service bx1-management.service bx1-body.service 2>/dev/null || true
systemctl disable bx1-touchscreen.service bx1-management.service bx1-body.service 2>/dev/null || true
[[ ! -e "$OLD_BODY" || -L "$OLD_BODY" ]] || { echo "legacy body path is occupied: $OLD_BODY" >&2; exit 3; }
[[ ! -e "$OLD_MGMT" || -L "$OLD_MGMT" ]] || { echo "legacy management path is occupied: $OLD_MGMT" >&2; exit 3; }
mkdir -p "$(dirname "$OLD_BODY")" "$(dirname "$OLD_MGMT")"
rsync -aHAX --numeric-ids "$BACKUP/body/" "$OLD_BODY/"
rsync -aHAX --numeric-ids "$BACKUP/management/" "$OLD_MGMT/"
if [[ -f "$BACKUP/bx1-web.service" ]]; then install -m644 "$BACKUP/bx1-web.service" /etc/systemd/system/bx1-web.service; fi
if [[ -f "$BACKUP/bx1-os-alpha.service" ]]; then install -m644 "$BACKUP/bx1-os-alpha.service" /etc/systemd/system/bx1-os-alpha.service; fi
if [[ -f "$BACKUP/bx1-touchscreen.service" ]]; then install -m644 "$BACKUP/bx1-touchscreen.service" /etc/systemd/system/bx1-touchscreen.service; fi
systemctl daemon-reload
for unit in bx1-web.service bx1-os-alpha.service bx1-touchscreen.service; do
  if [[ -s "$BACKUP/$unit.enabled" ]] && grep -q '^enabled' "$BACKUP/$unit.enabled"; then
    systemctl enable "$unit"
    systemctl start "$unit"
  else
    systemctl disable "$unit"
  fi
done
echo 'Legacy layout restored; verify ports and health manually.'
