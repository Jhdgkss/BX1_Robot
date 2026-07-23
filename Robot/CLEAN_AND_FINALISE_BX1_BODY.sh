#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
PROJECT="$(cd "$PROJECT" && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$PROJECT/backups/full_v10_31_$STAMP"

echo "============================================================"
echo " BX1 Body v10.31 - Clean Full Project Finaliser"
echo "============================================================"
echo "Project: $PROJECT"
echo "Backup : $BACKUP"
echo
echo "This preserves config, .venv, models, runtime and backups."
echo "It removes obsolete patch folders, duplicate source copies and caches."
echo

mkdir -p "$BACKUP"
if [[ -f "$PROJECT/python/config.json" ]]; then
  cp -a "$PROJECT/python/config.json" "$BACKUP/config.json"
fi
if [[ -f "$PROJECT/python/robot_profile.json" ]]; then
  cp -a "$PROJECT/python/robot_profile.json" "$BACKUP/robot_profile.json"
fi

find "$PROJECT" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
rm -rf "$PROJECT/files" "$PROJECT/update_files" "$PROJECT/docs/patch_history"
rm -f "$PROJECT"/APPLY_BX1_V*.sh
rm -f "$PROJECT"/INSTALL_FIRST_*.txt
rm -f "$PROJECT"/README_V10_*.txt
for old_readme in "$PROJECT"/README_V10_*.md; do
  [[ -e "$old_readme" ]] || continue
  [[ "$(basename "$old_readme")" == "README_V10_31.md" ]] || rm -f "$old_readme"
done
rm -f "$PROJECT"/VALIDATION_REPORT.txt "$PROJECT"/config_additions.json
rm -f "$PROJECT"/python/config.v10.*.defaults.json
rm -f "$PROJECT"/tools/migrate_v10_2*.py "$PROJECT"/tools/migrate_v10_30_config.py
rm -f "$PROJECT"/tools/test_v10_*.py

if [[ ! -f "$PROJECT/python/config.json" ]]; then
  cp "$PROJECT/python/config.example.json" "$PROJECT/python/config.json"
  echo "Created python/config.json from config.example.json"
fi

if [[ ! -x "$PROJECT/.venv/bin/python" ]]; then
  echo "Creating project virtual environment..."
  python3 -m venv --system-site-packages "$PROJECT/.venv"
fi

"$PROJECT/.venv/bin/python" -m pip install -r "$PROJECT/python/requirements.txt"
"$PROJECT/.venv/bin/python" "$PROJECT/tools/migrate_v10_31_config.py" "$PROJECT"
"$PROJECT/.venv/bin/python" -m py_compile \
  "$PROJECT/python/main.py" \
  "$PROJECT/python/audio_io.py" \
  "$PROJECT/python/bx1_robot_client.py" \
  "$PROJECT/python/web_control.py"

chmod +x "$PROJECT"/*.sh "$PROJECT"/tools/*.sh 2>/dev/null || true

if command -v systemctl >/dev/null 2>&1; then
  sudo "$PROJECT/tools/install_bx1_web_service.sh"
else
  echo "systemctl is unavailable; start the project with START_BX1_WEB.sh"
fi

echo
echo "BX1 Body v10.31 clean full project is ready."
echo "Primary STT: desktop Brain faster-whisper"
echo "Fallback STT: local Vosk when available"
echo "No MCU firmware was flashed."
