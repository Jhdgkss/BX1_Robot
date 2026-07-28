#!/usr/bin/env bash
set -Eeuo pipefail
PATCH_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$PATCH_ROOT/tools/patch_runtime.py" apply "$@"
