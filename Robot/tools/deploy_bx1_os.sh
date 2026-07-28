#!/usr/bin/env bash
set -Eeuo pipefail

echo "[BX1 DEPLOY] BX1 OS Alpha v0.2.0 side-by-side launcher"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/release_manifest.json" ] && [ -d "$SCRIPT_DIR/payload" ]; then
  RELEASE_ROOT="$SCRIPT_DIR"
  TOOL="$SCRIPT_DIR/payload/tools/deploy_bx1_os.py"
  if ! cmp -s "$SCRIPT_DIR/deploy_bx1_os.sh" \
    "$SCRIPT_DIR/payload/tools/deploy_bx1_os.sh"; then
    echo "[BX1 DEPLOY] ERROR: launcher differs from the verified payload" >&2
    exit 2
  fi
else
  RELEASE_ROOT="${BX1_RELEASE_ROOT:-}"
  TOOL="$SCRIPT_DIR/deploy_bx1_os.py"
fi

PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "[BX1 DEPLOY] ERROR: python3 is required" >&2
  exit 127
fi
if [ ! -f "$TOOL" ]; then
  echo "[BX1 DEPLOY] ERROR: deployment implementation is missing: $TOOL" >&2
  exit 2
fi

if [ -n "$RELEASE_ROOT" ]; then
  exec "$PYTHON_BIN" "$TOOL" --release-root "$RELEASE_ROOT" "$@"
fi
exec "$PYTHON_BIN" "$TOOL" "$@"
