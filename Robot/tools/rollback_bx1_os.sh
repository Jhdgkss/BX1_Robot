#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/release_manifest.json" ] && [ -d "$SCRIPT_DIR/payload" ]; then
  TOOL="$SCRIPT_DIR/payload/tools/rollback_bx1_os.py"
  if ! cmp -s "$SCRIPT_DIR/rollback_bx1_os.sh" \
    "$SCRIPT_DIR/payload/tools/rollback_bx1_os.sh"; then
    echo "[BX1 ROLLBACK] ERROR: launcher differs from the verified payload" >&2
    exit 2
  fi
else
  TOOL="$SCRIPT_DIR/rollback_bx1_os.py"
fi

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "[BX1 ROLLBACK] ERROR: python3 is required" >&2
  exit 127
fi
if [ ! -f "$TOOL" ]; then
  echo "[BX1 ROLLBACK] ERROR: rollback implementation is missing: $TOOL" >&2
  exit 2
fi
exec "$PYTHON_BIN" "$TOOL" "$@"
