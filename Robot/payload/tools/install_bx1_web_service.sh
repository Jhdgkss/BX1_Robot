#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="/etc/systemd/system/bx1-web.service"

chmod +x "$ROOT_DIR/main.py" "$ROOT_DIR/START_BX1_WEB.sh" "$ROOT_DIR/STOP_BX1_WEB.sh" \
  "$ROOT_DIR/tools/run_robot_body.sh" "$ROOT_DIR/tools/check_web_health.sh"

sudo tee "$SERVICE_FILE" >/dev/null <<EOF2
[Unit]
Description=BX1 UNO Q Body Client v10.42
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=arduino
WorkingDirectory=$ROOT_DIR
Environment=PYTHONUNBUFFERED=1
Environment=BX1_WEB_ENABLED=1
Environment=BX1_WEB_HOST=0.0.0.0
Environment=BX1_WEB_PORT=8088
ExecStart=$ROOT_DIR/tools/run_robot_body.sh
ExecStartPost=$ROOT_DIR/tools/check_web_health.sh
Restart=always
RestartSec=5
KillSignal=SIGTERM
TimeoutStartSec=35
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF2

sudo systemctl daemon-reload
sudo systemctl enable bx1-web.service
sudo systemctl restart bx1-web.service
sleep 2
sudo systemctl status bx1-web.service --no-pager -l || true
