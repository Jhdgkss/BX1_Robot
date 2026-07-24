#!/usr/bin/env bash
set -u

echo "=== BX1 GitHub service ==="
sudo systemctl status bx1-github.service --no-pager -l || true

echo
echo "=== Recent service log ==="
sudo journalctl -u bx1-github.service -n 100 --no-pager || true

echo
echo "=== Listening TCP ports ==="
ss -ltnp 2>/dev/null | grep -E ':(8088|8765|8091)\b' || echo "No expected BX1 TCP port detected."

echo
echo "=== Application path ==="
readlink -f /proc/$(systemctl show -p MainPID --value bx1-github.service)/cwd 2>/dev/null || true
