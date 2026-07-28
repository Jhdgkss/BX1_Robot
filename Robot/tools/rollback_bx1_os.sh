#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR=""
SERVICE_NAME="bx1-web.service"
AUTOMATIC=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: rollback_bx1_os.sh --backup PATH [options]
  --service NAME   systemd service name
  --automatic      Mark rollback as automatic
  --dry-run        Validate backup without restoring files
EOF
}

say() { printf '\n[BX1 ROLLBACK] %s\n' "$*"; }
fail() { printf '\n[BX1 ROLLBACK] ERROR: %s\n' "$*" >&2; return 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup) BACKUP_DIR="$2"; shift 2 ;;
    --service) SERVICE_NAME="$2"; shift 2 ;;
    --automatic) AUTOMATIC=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "Unknown argument: $1"; usage; exit 2 ;;
  esac
done
if [ -z "$BACKUP_DIR" ]; then
  fail "--backup is required"
  exit 2
fi
PYTHON_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON_BIN" ]; then
  fail "python3 is required"
  exit 127
fi
BACKUP_DIR="$("$PYTHON_BIN" - "$BACKUP_DIR" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]).expanduser().resolve()
if str(p) == "/" or len(p.parts) < 3:
    raise SystemExit("unsafe backup path: %s" % p)
print(p)
PY
)"
for required in deployment_manifest.json deployed_release_manifest.json installation.tar.gz "systemd/$SERVICE_NAME"; do
  if [ ! -s "$BACKUP_DIR/$required" ]; then
    fail "Backup is incomplete: $required"
    exit 2
  fi
done
tar -tzf "$BACKUP_DIR/installation.tar.gz" >/dev/null

INSTALL_ROOT="$("$PYTHON_BIN" - "$BACKUP_DIR/deployment_manifest.json" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("schema") != "bx1.deployment.backup.v1" or not value.get("backup_complete"):
    raise SystemExit("backup manifest is invalid or incomplete")
p = pathlib.Path(value["install_root"]).resolve()
if str(p) == "/" or len(p.parts) < 3:
    raise SystemExit("unsafe install root: %s" % p)
print(p)
PY
)"
if [ "$DRY_RUN" -eq 1 ]; then
  say "Rollback backup validation passed"
  printf 'Backup: %s\nInstall root: %s\nService: %s\n' \
    "$BACKUP_DIR" "$INSTALL_ROOT" "$SERVICE_NAME"
  exit 0
fi
if ! command -v systemctl >/dev/null 2>&1; then
  fail "systemd is required for rollback"
  exit 2
fi
if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
else
  command -v sudo >/dev/null 2>&1 || fail "sudo is required"
  SUDO=(sudo)
fi

say "Stopping the deployed service"
"${SUDO[@]}" systemctl stop "$SERVICE_NAME" || true

say "Removing only files listed in the deployed release manifest"
"$PYTHON_BIN" - "$INSTALL_ROOT" "$BACKUP_DIR/deployed_release_manifest.json" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
manifest = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
if manifest.get("schema") != "bx1.deployment.release.v1":
    raise SystemExit("invalid deployed release manifest")
for entry in manifest.get("files", []):
    relative = pathlib.PurePosixPath(str(entry.get("path", "")))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise SystemExit("unsafe deployed path: %s" % relative)
    target = root.joinpath(*relative.parts)
    if target.is_symlink():
        target.unlink()
        continue
    if target.exists():
        resolved = target.resolve()
        if root not in resolved.parents:
            raise SystemExit("deployed path escaped install root: %s" % target)
        if target.is_file():
            target.unlink()
        elif target.is_dir() and not any(target.iterdir()):
            target.rmdir()
PY

say "Restoring the complete pre-deployment installation archive"
"$PYTHON_BIN" - "$INSTALL_ROOT" "$BACKUP_DIR/installation.tar.gz" <<'PY'
import pathlib, tarfile, sys
root = pathlib.Path(sys.argv[1]).resolve()
archive = pathlib.Path(sys.argv[2]).resolve()
with tarfile.open(archive, "r:gz") as bundle:
    members = bundle.getmembers()
    for member in members:
        target = (root / member.name).resolve()
        if target != root and root not in target.parents:
            raise SystemExit("unsafe backup archive member: %s" % member.name)
        if member.issym() or member.islnk():
            link = pathlib.PurePosixPath(member.linkname)
            if link.is_absolute():
                raise SystemExit("unsafe absolute backup link: %s" % member.name)
            link_target = (target.parent / pathlib.Path(*link.parts)).resolve()
            if link_target != root and root not in link_target.parents:
                raise SystemExit("unsafe backup link target: %s" % member.name)
    bundle.extractall(root)
PY

SERVICE_PATH="$("$PYTHON_BIN" - "$BACKUP_DIR/deployment_manifest.json" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["service_path"])
PY
)"
if [ "$SERVICE_PATH" != "/etc/systemd/system/$SERVICE_NAME" ]; then
  "${SUDO[@]}" rm -f "/etc/systemd/system/$SERVICE_NAME"
fi
"${SUDO[@]}" install -m 0644 "$BACKUP_DIR/systemd/$SERVICE_NAME" "$SERVICE_PATH"
if [ -d "$BACKUP_DIR/systemd/${SERVICE_NAME}.d" ]; then
  "${SUDO[@]}" mkdir -p "/etc/systemd/system/${SERVICE_NAME}.d"
  "${SUDO[@]}" cp -a "$BACKUP_DIR/systemd/${SERVICE_NAME}.d/." \
    "/etc/systemd/system/${SERVICE_NAME}.d/"
fi
"${SUDO[@]}" systemctl daemon-reload

SERVICE_WAS_ENABLED="$("$PYTHON_BIN" - "$BACKUP_DIR/deployment_manifest.json" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print("1" if value.get("service_was_enabled") else "0")
PY
)"
if [ "$SERVICE_WAS_ENABLED" = "1" ]; then
  "${SUDO[@]}" systemctl enable "$SERVICE_NAME"
else
  "${SUDO[@]}" systemctl disable "$SERVICE_NAME" || true
fi
"${SUDO[@]}" systemctl restart "$SERVICE_NAME"
sleep 2
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  fail "Previous service did not restart after rollback"
  "${SUDO[@]}" systemctl status "$SERVICE_NAME" --no-pager -l || true
  exit 1
fi

CONFIG_SHA_EXPECTED="$("$PYTHON_BIN" - "$BACKUP_DIR/deployment_manifest.json" <<'PY'
import json, pathlib, sys
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value["config_sha256"])
PY
)"
CONFIG_SHA_ACTUAL="$(sha256sum "$INSTALL_ROOT/python/config.json" | awk '{print $1}')"
if [ "$CONFIG_SHA_EXPECTED" != "$CONFIG_SHA_ACTUAL" ]; then
  fail "Configuration hash did not restore correctly"
  exit 1
fi

export BX1_BACKUP_DIR="$BACKUP_DIR"
export BX1_INSTALL_ROOT="$INSTALL_ROOT"
export BX1_SERVICE_NAME="$SERVICE_NAME"
export BX1_ROLLBACK_AUTOMATIC="$AUTOMATIC"
"$PYTHON_BIN" - <<'PY'
import json, os, pathlib, time
report = {
    "schema": "bx1.deployment.rollback.v1",
    "status": "ROLLED_BACK",
    "completed_at": time.time(),
    "automatic": os.environ["BX1_ROLLBACK_AUTOMATIC"] == "1",
    "backup_location": os.environ["BX1_BACKUP_DIR"],
    "install_root": os.environ["BX1_INSTALL_ROOT"],
    "service_name": os.environ["BX1_SERVICE_NAME"],
    "previous_service_restarted": True,
    "configuration_restored": True,
    "partial_deployment_remaining": False,
}
path = pathlib.Path(os.environ["BX1_BACKUP_DIR"]) / "rollback_report.json"
path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

say "Rollback completed and previous service restarted"
printf 'Backup: %s\nReport: %s\n' \
  "$BACKUP_DIR" "$BACKUP_DIR/rollback_report.json"
