#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="${BX1_ROOT:-/home/arduino/BX1}"
TARGET="${1:?usage: rollback_bx1_unified.sh <release-version>}"
RELEASE="$ROOT/releases/$TARGET"
[[ -d "$RELEASE" ]] || { echo "Missing release: $RELEASE" >&2; exit 1; }
ln -sfn "$RELEASE" "$ROOT/current.next"
mv -Tf "$ROOT/current.next" "$ROOT/current"
systemctl restart bx1-body.service bx1-management.service bx1-touchscreen.service
systemctl is-active bx1-body.service bx1-management.service
ss -ltn | grep -E ':8088 |:8089 '
