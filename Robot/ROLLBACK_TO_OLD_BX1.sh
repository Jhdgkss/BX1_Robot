#!/usr/bin/env bash
set -Eeuo pipefail

echo "Restoring the original BX1 startup service..."

sudo systemctl stop bx1-github.service 2>/dev/null || true
sudo systemctl disable bx1-github.service 2>/dev/null || true

if [[ -f /etc/systemd/system/bx1-web.service || -f /lib/systemd/system/bx1-web.service ]]; then
  sudo systemctl enable bx1-web.service
  sudo systemctl restart bx1-web.service
  echo "Restored bx1-web.service."
elif [[ -f /etc/systemd/system/bx1-robot-body.service || -f /lib/systemd/system/bx1-robot-body.service ]]; then
  sudo systemctl enable bx1-robot-body.service
  sudo systemctl restart bx1-robot-body.service
  echo "Restored bx1-robot-body.service."
else
  echo "No previous BX1 service file was found."
  echo "The old application is still at /home/arduino/Arduino_Q_Client_V1."
  exit 1
fi

sudo systemctl daemon-reload
echo
echo "Rollback complete."
