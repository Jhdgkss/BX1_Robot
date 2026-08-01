#!/usr/bin/env bash
set -Eeuo pipefail
umask 027
ROOT="${BX1_ROOT:-/home/arduino/BX1}"
OLD_BODY="${BX1_OLD_BODY:-/home/arduino/Arduino_Q_Client_V1}"
OLD_MGMT="${BX1_OLD_MANAGEMENT:-/home/arduino/BX1_OS}"
MODE=cutover
VERSION=""
SOURCE_BODY="$OLD_BODY"
SOURCE_MGMT="$OLD_MGMT"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE=dry-run; shift ;;
    --prepare-only) MODE=prepare-only; shift ;;
    --version) VERSION="${2:?--version requires a value}"; shift 2 ;;
    --body-source) SOURCE_BODY="${2:?--body-source requires a value}"; shift 2 ;;
    --management-source) SOURCE_MGMT="${2:?--management-source requires a value}"; shift 2 ;;
    --help) echo 'usage: migrate_bx1_unified.sh [--dry-run|--prepare-only] --version VERSION'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$VERSION" ]] || { echo '--version is required' >&2; exit 2; }
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE="$ROOT/releases/$VERSION"
STAGE="$ROOT/staging/$VERSION-$STAMP"
BACKUP="$ROOT/backups/pre-unified-$STAMP"
TEMPLATE_ROOT="${BX1_TEMPLATE_ROOT:-$(dirname "$0")}"
log(){ printf '[%s] %s\n' "$MODE" "$*"; }
die(){ log "BLOCKED: $*" >&2; exit 1; }
run(){ log "+ $*"; [[ "$MODE" == dry-run ]] || "$@"; }
COPY_EXCLUDES=(.venv runtime logs cache diagnostic_traces browser-profiles browser_profile profiles generated temporary tmp)
if command -v rsync >/dev/null 2>&1; then
  COPY_METHOD=rsync
elif command -v tar >/dev/null 2>&1; then
  COPY_METHOD='tar fallback'
else
  die 'no supported copy method available (install neither automatically; provide rsync or tar)'
fi
copy_tree(){
  local source="$1" destination="$2" delete_mode="${3:-false}" exclude_mode="${4:-true}"
  log "Copy method: $COPY_METHOD ($source -> $destination)"
  if [[ "$MODE" == dry-run ]]; then return 0; fi
  mkdir -p "$destination"
  if [[ "$COPY_METHOD" == rsync ]]; then
    local args=(-aHAX --numeric-ids)
    [[ "$delete_mode" == true ]] && args+=(--delete)
    if [[ "$exclude_mode" == true ]]; then
      for excluded in "${COPY_EXCLUDES[@]}"; do args+=(--exclude="$excluded/"); done
    fi
    rsync "${args[@]}" "$source/" "$destination/"
  else
    local tar_args=()
    if [[ "$exclude_mode" == true ]]; then
      for excluded in "${COPY_EXCLUDES[@]}"; do
        tar_args+=(--exclude="./$excluded" --exclude="./$excluded/*")
      done
    fi
    tar -C "$source" "${tar_args[@]}" -cf - . | tar -C "$destination" -xf -
  fi
}
[[ $EUID -eq 0 ]] || die 'root privileges are required'
[[ -d "$SOURCE_BODY" && -d "$SOURCE_MGMT" ]] || die 'source roots are missing'
[[ ! -e "$RELEASE" ]] || die "release already exists: $RELEASE"
log "Copy method: $COPY_METHOD"

if [[ "$MODE" == dry-run ]]; then
  log 'No filesystem, process, symlink, rename or service operation will run.'
  for path in "$SOURCE_BODY/.venv/bin/python" "$SOURCE_MGMT/.venv/bin/python" "$SOURCE_BODY/main.py" "$SOURCE_BODY/python/main.py" "$SOURCE_MGMT/python/bx1_management/server.py"; do
    [[ -e "$path" ]] && log "verified $path" || log "BLOCKED missing $path"
  done
  systemctl list-unit-files bx1-web.service bx1-os-alpha.service bx1-touchscreen.service bx1-kiosk.service 2>&1 || true
  for unit in bx1-body.service bx1-management.service bx1-touchscreen.service; do systemd-analyze verify "$TEMPLATE_ROOT/$unit" 2>&1 || log "BLOCKED unit verification: $unit"; done
  ps -eo pid,args | grep -E 'main.py|bx1_management|run_bx1|touchscreen' | grep -v grep || true
  log "would backup to $BACKUP, stage $STAGE, create $RELEASE, switch current, install units and validate"
  exit 0
fi

mkdir -p "$ROOT"/{releases,config,runtime,logs,backups,staging,venvs} "$BACKUP" "$STAGE/body" "$STAGE/management" "$STAGE/shared"
copy_tree "$OLD_BODY" "$BACKUP/body" false false
copy_tree "$OLD_MGMT" "$BACKUP/management" false false
for unit in bx1-web.service bx1-os-alpha.service bx1-touchscreen.service; do
  run bash -c "systemctl cat '$unit' > '$BACKUP/$unit' 2>/dev/null || true"
  run bash -c "systemctl is-enabled '$unit' > '$BACKUP/$unit.enabled' 2>/dev/null || true"
done
copy_tree "$SOURCE_BODY" "$STAGE/body" true
copy_tree "$SOURCE_MGMT" "$STAGE/management" true
for f in config.json robot_profile.json; do
  [[ -e "$SOURCE_BODY/python/$f" ]] && run install -Dm640 "$SOURCE_BODY/python/$f" "$ROOT/config/$f"
done
[[ -e "$SOURCE_MGMT/python/config.json" ]] && run install -Dm640 "$SOURCE_MGMT/python/config.json" "$ROOT/config/management.json"
[[ -e "$SOURCE_BODY/.venv/bin/python" ]] && copy_tree "$SOURCE_BODY/.venv" "$ROOT/venvs/body" true false
[[ -e "$SOURCE_MGMT/.venv/bin/python" ]] && copy_tree "$SOURCE_MGMT/.venv" "$ROOT/venvs/management" true false
run bash -c "grep -RIl '$OLD_BODY' '$ROOT/venvs/body/bin' 2>/dev/null | xargs -r sed -i 's|$OLD_BODY|$ROOT/venvs/body|g'"
run bash -c "grep -RIl '$OLD_MGMT' '$ROOT/venvs/management/bin' 2>/dev/null | xargs -r sed -i 's|$OLD_MGMT|$ROOT/venvs/management|g'"
run ln -sfn "$ROOT/runtime" "$STAGE/body/runtime"
run ln -sfn "$ROOT/logs" "$STAGE/body/logs"
run ln -sfn "$ROOT/runtime" "$STAGE/management/runtime"
run ln -sfn "$ROOT/logs" "$STAGE/management/logs"
run mv "$STAGE" "$RELEASE"
BODY_PY="$ROOT/venvs/body/bin/python"
MGMT_PY="$ROOT/venvs/management/bin/python"
run "$BODY_PY" -m py_compile "$RELEASE/body/main.py" "$RELEASE/body/python/main.py"
run "$MGMT_PY" -m py_compile "$RELEASE/management/python/bx1_management/server.py"
run node --check "$RELEASE/management/python/bx1_management/static/app.js"
run bash -n "$RELEASE/body/tools/run_robot_body.sh"
run bash -n "$RELEASE/management/tools/run_bx1_os_management.sh"
run bash -n "$RELEASE/management/tools/bx1_touchscreen_kiosk.sh"
run python3 - "$RELEASE/manifest.json" "$VERSION" "$STAMP" <<'PY'
import hashlib, json, os, subprocess, sys
manifest, version, stamp = sys.argv[1:]
root = os.path.dirname(manifest)
files = {}
for base, _, names in os.walk(root):
    for name in names:
        path = os.path.join(base, name)
        if path == manifest:
            continue
        with open(path, 'rb') as fh:
            files[os.path.relpath(path, root).replace(os.sep, '/')] = hashlib.sha256(fh.read()).hexdigest()
try:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
except Exception:
    commit = 'unknown'
try:
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip())
except Exception:
    dirty = True
json.dump({'release_version': version, 'robot_body_version': version, 'management_version': version,
           'compatible_brain_version': 'v0.10.3-voice-stability', 'git_commit': commit,
           'dirty_working_tree': dirty, 'deployment_timestamp': stamp,
           'previous_release': os.path.realpath(os.path.join(root, '..', 'current')),
           'configuration_schema_version': 1, 'source_file_sha256': files,
           'installed_file_sha256': files}, open(manifest, 'w'), indent=2)
PY
[[ "$MODE" == prepare-only ]] && { log "prepare-only complete: $RELEASE"; exit 0; }

rollback(){
  log 'automatic rollback starting'
  systemctl stop bx1-touchscreen.service bx1-management.service bx1-body.service 2>/dev/null || true
  [[ -L "$OLD_BODY" ]] && unlink "$OLD_BODY" || true
  [[ -L "$OLD_MGMT" ]] && unlink "$OLD_MGMT" || true
  [[ ! -e "$OLD_BODY" ]] && copy_tree "$BACKUP/body" "$OLD_BODY" false false || true
  [[ ! -e "$OLD_MGMT" ]] && copy_tree "$BACKUP/management" "$OLD_MGMT" false false || true
  systemctl daemon-reload || true
  for unit in bx1-web.service bx1-os-alpha.service bx1-touchscreen.service; do
    if [[ -s "$BACKUP/$unit.enabled" ]] && grep -q '^enabled' "$BACKUP/$unit.enabled"; then systemctl enable "$unit" || true; else systemctl disable "$unit" || true; fi
  done
  systemctl enable --now bx1-web.service bx1-os-alpha.service bx1-touchscreen.service || true
}
trap rollback ERR
for unit in bx1-web.service bx1-os-alpha.service bx1-touchscreen.service bx1-kiosk.service; do
  run systemctl stop "$unit"
done
for pid in $(ps -eo pid=,args= | awk '/bx1_management --config/ {print $1}'); do
  run kill -TERM "$pid"
done
[[ ! -e "$OLD_BODY" || -L "$OLD_BODY" ]] || run mv "$OLD_BODY" "$BACKUP/Arduino_Q_Client_V1"
[[ ! -e "$OLD_MGMT" || -L "$OLD_MGMT" ]] || run mv "$OLD_MGMT" "$BACKUP/BX1_OS"
run ln -sfn "$RELEASE" "$ROOT/current.next"
run mv -Tf "$ROOT/current.next" "$ROOT/current"
run ln -sfn "$ROOT/current/body" "$OLD_BODY"
run ln -sfn "$ROOT/current/management" "$OLD_MGMT"
for unit in bx1-body.service bx1-management.service bx1-touchscreen.service; do
  run install -Dm644 "$TEMPLATE_ROOT/$unit" "/etc/systemd/system/$unit"
done
run systemctl daemon-reload
run systemctl enable --now bx1-body.service bx1-management.service bx1-touchscreen.service
run "$(dirname "$0")/validate_bx1_unified.sh"
trap - ERR
log "cutover complete: $RELEASE; backup: $BACKUP"
