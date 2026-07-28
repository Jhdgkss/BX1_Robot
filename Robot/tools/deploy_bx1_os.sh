#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_ROOT="$SCRIPT_DIR"
INSTALL_ROOT="/home/arduino/Arduino_Q_Client_V1"
SERVICE_NAME="bx1-web.service"
SERVICE_USER="arduino"
STATUS_URL="http://127.0.0.1:8088/api/status"
BACKUP_ROOT=""
DRY_RUN=0
BACKUP_COMPLETE=0
CHANGES_STARTED=0
ROLLBACK_RUNNING=0
BACKUP_DIR=""

usage() {
  cat <<'EOF'
Usage: deploy_bx1_os.sh [options]
  --release-root PATH   Extracted BX1 release directory
  --install-root PATH   Existing Robot installation
  --backup-root PATH    Backup parent (default: INSTALL_ROOT/backups)
  --service NAME        systemd service (default: bx1-web.service)
  --service-user USER   systemd service user (default: arduino)
  --status-url URL      Robot status endpoint
  --dry-run             Verify package and prerequisites without changing files
EOF
}

say() { printf '\n[BX1 DEPLOY] %s\n' "$*"; }
fail() { printf '\n[BX1 DEPLOY] ERROR: %s\n' "$*" >&2; return 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --release-root) RELEASE_ROOT="$2"; shift 2 ;;
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --backup-root) BACKUP_ROOT="$2"; shift 2 ;;
    --service) SERVICE_NAME="$2"; shift 2 ;;
    --service-user) SERVICE_USER="$2"; shift 2 ;;
    --status-url) STATUS_URL="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown argument: $1"; usage; exit 2 ;;
  esac
done

RELEASE_ROOT="$(cd "$RELEASE_ROOT" && pwd)"
if [ ! -f "$RELEASE_ROOT/release_manifest.json" ] || [ ! -d "$RELEASE_ROOT/payload" ]; then
  fail "Release root must contain release_manifest.json and payload/"
  exit 2
fi
if [ ! -f "$RELEASE_ROOT/qualify_bx1_alpha.py" ] || [ ! -f "$RELEASE_ROOT/rollback_bx1_os.sh" ]; then
  fail "Release qualification or rollback utility is missing"
  exit 2
fi
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  fail "python3 is required"
  exit 127
fi

INSTALL_ROOT="$("$PYTHON_BIN" - "$INSTALL_ROOT" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]).expanduser().resolve()
if str(p) == "/" or len(p.parts) < 3:
    raise SystemExit("unsafe install root: %s" % p)
print(p)
PY
)"
BACKUP_ROOT="${BACKUP_ROOT:-$INSTALL_ROOT/backups}"
BACKUP_ROOT="$("$PYTHON_BIN" - "$BACKUP_ROOT" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]).expanduser().resolve()
if str(p) == "/" or len(p.parts) < 3:
    raise SystemExit("unsafe backup root: %s" % p)
print(p)
PY
)"

say "Verifying release hashes and manifest"
"$PYTHON_BIN" "$RELEASE_ROOT/qualify_bx1_alpha.py" \
  --verify-release "$RELEASE_ROOT" >/dev/null
cmp -s "$RELEASE_ROOT/deploy_bx1_os.sh" \
  "$RELEASE_ROOT/payload/tools/deploy_bx1_os.sh" \
  || fail "Deployment launcher differs from verified payload"
cmp -s "$RELEASE_ROOT/rollback_bx1_os.sh" \
  "$RELEASE_ROOT/payload/tools/rollback_bx1_os.sh" \
  || fail "Rollback launcher differs from verified payload"
cmp -s "$RELEASE_ROOT/qualify_bx1_alpha.py" \
  "$RELEASE_ROOT/payload/tools/qualify_bx1_alpha.py" \
  || fail "Qualification launcher differs from verified payload"

if [ "$DRY_RUN" -eq 1 ]; then
  [ -d "$INSTALL_ROOT" ] || fail "Install root does not exist: $INSTALL_ROOT"
  [ -f "$INSTALL_ROOT/python/config.json" ] || fail "Preserved config is missing"
  command -v systemctl >/dev/null 2>&1 || fail "systemctl is unavailable"
  say "Dry run passed"
  printf 'Release: %s\nInstall: %s\nBackup parent: %s\nService: %s\n' \
    "$RELEASE_ROOT" "$INSTALL_ROOT" "$BACKUP_ROOT" "$SERVICE_NAME"
  exit 0
fi

if [ ! -d "$INSTALL_ROOT" ] || [ ! -f "$INSTALL_ROOT/python/config.json" ]; then
  fail "Existing installation/configuration was not found at $INSTALL_ROOT"
  exit 2
fi
if ! command -v systemctl >/dev/null 2>&1; then
  fail "systemd is required for Alpha deployment"
  exit 2
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
else
  command -v sudo >/dev/null 2>&1 || fail "sudo is required"
  SUDO=(sudo)
fi

SERVICE_PATH=""
for candidate in "/etc/systemd/system/$SERVICE_NAME" "/lib/systemd/system/$SERVICE_NAME" "/usr/lib/systemd/system/$SERVICE_NAME"; do
  if [ -f "$candidate" ]; then
    SERVICE_PATH="$candidate"
    break
  fi
done
if [ -z "$SERVICE_PATH" ]; then
  fail "Existing systemd service file was not found"
  exit 2
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/${STAMP}_ALPHA"
if [ -e "$BACKUP_DIR" ]; then
  fail "Backup path already exists: $BACKUP_DIR"
  exit 2
fi
mkdir -p "$BACKUP_DIR/configuration" "$BACKUP_DIR/systemd" "$BACKUP_DIR/startup"

SERVICE_WAS_ACTIVE=0
SERVICE_WAS_ENABLED=0
systemctl is-active --quiet "$SERVICE_NAME" && SERVICE_WAS_ACTIVE=1 || true
systemctl is-enabled --quiet "$SERVICE_NAME" && SERVICE_WAS_ENABLED=1 || true
LIVE_GIT_COMMIT="unavailable"
if [ -d "$INSTALL_ROOT/.git" ]; then
  LIVE_GIT_COMMIT="$(git -C "$INSTALL_ROOT" rev-parse HEAD 2>/dev/null || printf unavailable)"
fi
CONFIG_SHA_BEFORE="$(sha256sum "$INSTALL_ROOT/python/config.json" | awk '{print $1}')"

say "Creating required pre-deployment backup: $BACKUP_DIR"
ARCHIVE_PARTIAL="$BACKUP_DIR/installation.tar.gz.partial"
tar -czf "$ARCHIVE_PARTIAL" \
  --exclude='./.venv' \
  --exclude='./runtime' \
  --exclude='./models' \
  --exclude='./logs' \
  --exclude='./backups' \
  --exclude='./.git' \
  --exclude='*/__pycache__' \
  -C "$INSTALL_ROOT" .
tar -tzf "$ARCHIVE_PARTIAL" >/dev/null
mv "$ARCHIVE_PARTIAL" "$BACKUP_DIR/installation.tar.gz"

cp -a "$INSTALL_ROOT/python/config.json" "$BACKUP_DIR/configuration/config.json"
find "$INSTALL_ROOT/python" -maxdepth 1 -type f \
  \( -name 'robot_profile*.json' -o -name '*calibration*.json' \) \
  -exec cp -a {} "$BACKUP_DIR/configuration/" \;
"${SUDO[@]}" cp -a "$SERVICE_PATH" "$BACKUP_DIR/systemd/$SERVICE_NAME"
if [ -d "/etc/systemd/system/${SERVICE_NAME}.d" ]; then
  "${SUDO[@]}" cp -a "/etc/systemd/system/${SERVICE_NAME}.d" "$BACKUP_DIR/systemd/"
fi
for relative in main.py START_BX1_WEB.sh STOP_BX1_WEB.sh REPAIR_BX1_STARTUP.sh \
  tools/run_robot_body.sh tools/check_web_health.sh tools/install_bx1_web_service.sh; do
  if [ -f "$INSTALL_ROOT/$relative" ]; then
    destination="$BACKUP_DIR/startup/$relative"
    mkdir -p "$(dirname "$destination")"
    cp -a "$INSTALL_ROOT/$relative" "$destination"
  fi
done
cp "$RELEASE_ROOT/release_manifest.json" "$BACKUP_DIR/deployed_release_manifest.json"

export BX1_BACKUP_DIR="$BACKUP_DIR"
export BX1_INSTALL_ROOT="$INSTALL_ROOT"
export BX1_SERVICE_NAME="$SERVICE_NAME"
export BX1_SERVICE_PATH="$SERVICE_PATH"
export BX1_SERVICE_WAS_ACTIVE="$SERVICE_WAS_ACTIVE"
export BX1_SERVICE_WAS_ENABLED="$SERVICE_WAS_ENABLED"
export BX1_LIVE_GIT_COMMIT="$LIVE_GIT_COMMIT"
export BX1_CONFIG_SHA="$CONFIG_SHA_BEFORE"
"$PYTHON_BIN" - <<'PY'
import json, os, pathlib, time
manifest = {
    "schema": "bx1.deployment.backup.v1",
    "created_at": time.time(),
    "install_root": os.environ["BX1_INSTALL_ROOT"],
    "service_name": os.environ["BX1_SERVICE_NAME"],
    "service_path": os.environ["BX1_SERVICE_PATH"],
    "service_was_active": os.environ["BX1_SERVICE_WAS_ACTIVE"] == "1",
    "service_was_enabled": os.environ["BX1_SERVICE_WAS_ENABLED"] == "1",
    "live_git_commit": os.environ["BX1_LIVE_GIT_COMMIT"],
    "config_sha256": os.environ["BX1_CONFIG_SHA"],
    "installation_archive": "installation.tar.gz",
    "backup_complete": True,
}
path = pathlib.Path(os.environ["BX1_BACKUP_DIR"]) / "deployment_manifest.json"
path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
test -s "$BACKUP_DIR/deployment_manifest.json"
test -s "$BACKUP_DIR/installation.tar.gz"
test -s "$BACKUP_DIR/configuration/config.json"
test -s "$BACKUP_DIR/systemd/$SERVICE_NAME"
BACKUP_COMPLETE=1

rollback_on_failure() {
  code=$?
  trap - ERR INT TERM
  if [ "$CHANGES_STARTED" -eq 1 ] && [ "$BACKUP_COMPLETE" -eq 1 ] && [ "$ROLLBACK_RUNNING" -eq 0 ]; then
    ROLLBACK_RUNNING=1
    printf '\n[BX1 DEPLOY] Qualification/startup failed; rolling back automatically.\n' >&2
    "$RELEASE_ROOT/rollback_bx1_os.sh" \
      --backup "$BACKUP_DIR" \
      --service "$SERVICE_NAME" \
      --automatic || true
  fi
  printf '[BX1 DEPLOY] Deployment failed with exit %s. Backup: %s\n' "$code" "$BACKUP_DIR" >&2
  exit "$code"
}
trap rollback_on_failure ERR INT TERM

say "Stopping Robot service after backup verification"
"${SUDO[@]}" systemctl stop "$SERVICE_NAME"
CHANGES_STARTED=1

say "Installing verified BX1 OS Alpha payload while preserving user configuration"
tar -cf - -C "$RELEASE_ROOT/payload" . | tar -xf - -C "$INSTALL_ROOT"
CONFIG_SHA_AFTER="$(sha256sum "$INSTALL_ROOT/python/config.json" | awk '{print $1}')"
if [ "$CONFIG_SHA_AFTER" != "$CONFIG_SHA_BEFORE" ]; then
  fail "Preserved config.json changed during payload installation"
fi
chmod +x "$INSTALL_ROOT/main.py" "$INSTALL_ROOT/tools/"*.sh

SERVICE_TEMP="$(mktemp)"
sed \
  -e "s|/home/arduino/Arduino_Q_Client_V1|$INSTALL_ROOT|g" \
  -e "s|^User=.*|User=$SERVICE_USER|" \
  "$INSTALL_ROOT/service/bx1-web.service" > "$SERVICE_TEMP"
"${SUDO[@]}" install -m 0644 "$SERVICE_TEMP" "/etc/systemd/system/$SERVICE_NAME"
rm -f "$SERVICE_TEMP"
"${SUDO[@]}" systemctl daemon-reload
"${SUDO[@]}" systemctl enable "$SERVICE_NAME"
"${SUDO[@]}" systemctl restart "$SERVICE_NAME"

REPORT_DIR="$INSTALL_ROOT/deployment_reports"
mkdir -p "$REPORT_DIR"
QUALIFICATION_REPORT="$BACKUP_DIR/qualification_report.json"
say "Running strict post-deployment qualification"
"$PYTHON_BIN" "$INSTALL_ROOT/tools/qualify_bx1_alpha.py" \
  --install-root "$INSTALL_ROOT" \
  --service-name "$SERVICE_NAME" \
  --status-url "$STATUS_URL" \
  --output "$QUALIFICATION_REPORT"
cp "$QUALIFICATION_REPORT" "$REPORT_DIR/latest_qualification_report.json"

export BX1_QUALIFICATION_REPORT="$QUALIFICATION_REPORT"
export BX1_RELEASE_MANIFEST="$RELEASE_ROOT/release_manifest.json"
export BX1_DEPLOYMENT_REPORT="$BACKUP_DIR/deployment_report.json"
"$PYTHON_BIN" - <<'PY'
import json, os, pathlib, time
release = json.loads(pathlib.Path(os.environ["BX1_RELEASE_MANIFEST"]).read_text(encoding="utf-8"))
qualification = json.loads(pathlib.Path(os.environ["BX1_QUALIFICATION_REPORT"]).read_text(encoding="utf-8"))
report = {
    "schema": "bx1.deployment.report.v1",
    "milestone": "BX1 OS Alpha",
    "status": "DEPLOYED",
    "completed_at": time.time(),
    "install_root": os.environ["BX1_INSTALL_ROOT"],
    "backup_location": os.environ["BX1_BACKUP_DIR"],
    "service_name": os.environ["BX1_SERVICE_NAME"],
    "source_git_commit": release.get("source_git_commit"),
    "source_worktree_dirty": release.get("source_worktree_dirty"),
    "installed_files": [item["path"] for item in release.get("files", [])],
    "qualification_passed": qualification.get("passed", False),
    "rollback_used": False,
    "user_configuration_preserved": True,
    "firmware_changed": False,
}
pathlib.Path(os.environ["BX1_DEPLOYMENT_REPORT"]).write_text(
    json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY
cp "$BACKUP_DIR/deployment_report.json" "$REPORT_DIR/latest_deployment_report.json"

trap - ERR INT TERM
say "BX1 OS Alpha deployment qualified successfully"
printf 'Backup: %s\nReport: %s\nService: %s\n' \
  "$BACKUP_DIR" "$BACKUP_DIR/deployment_report.json" "$SERVICE_NAME"
