#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY="./.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[BX1] Missing venv Python at $PY"
  echo "[BX1] Run the project install first, or activate the venv manually."
  exit 1
fi
mkdir -p runtime/config_backups
if [ -f python/config.json ]; then
  cp python/config.json "runtime/config_backups/config_before_v10_19_$(date +%Y%m%d_%H%M%S).json"
fi
"$PY" - <<'PY'
import json
from pathlib import Path
p = Path('python/config.json')
cfg = json.loads(p.read_text(encoding='utf-8'))

def set_default(key, value):
    if key not in cfg or cfg.get(key) in (None, ''):
        cfg[key] = value

# Do not wipe live settings.  These are the minimum settings that must survive patches.
cfg['web_enabled'] = True
cfg['web_host'] = str(cfg.get('web_host') or '0.0.0.0')
cfg['web_port'] = int(cfg.get('web_port') or 8088)
# Make speech capture long enough for normal spoken questions.
try:
    if float(cfg.get('record_seconds', 5)) < 8:
        cfg['record_seconds'] = 10
except Exception:
    cfg['record_seconds'] = 10
set_default('wake_command_window_s', 20.0)
set_default('conversation_followup_window_s', 120.0)
set_default('wake_after_reply_guard_s', 1.5)
set_default('auto_camera_on_vision_request', True)
set_default('camera_enabled', True)
set_default('app_version', 'v10.19-vision-mcu-bridge-stability')

extra_phrases = [
    'what am i holding', 'what i am holding', "what i'm holding", 'what i was holding',
    'what is in my hand', "what's in my hand", 'what do i have in my hand',
    'what do i have here', 'what am i showing you', 'look at my hand',
    'identify what i am holding', 'what is this', "what's this", 'what is that', "what's that",
]
raw = cfg.get('vision_trigger_phrases', [])
if isinstance(raw, str):
    phrases = [x.strip() for x in raw.replace(',', '\n').splitlines() if x.strip()]
elif isinstance(raw, list):
    phrases = [str(x).strip() for x in raw if str(x).strip()]
else:
    phrases = []
seen = {x.lower(): x for x in phrases}
for phrase in extra_phrases:
    if phrase.lower() not in seen:
        phrases.append(phrase)
        seen[phrase.lower()] = phrase
cfg['vision_trigger_phrases'] = phrases
p.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
print('[BX1] Runtime config repaired without wiping live settings.')
print('[BX1] web_enabled:', cfg.get('web_enabled'))
print('[BX1] web:', cfg.get('web_host'), cfg.get('web_port'))
print('[BX1] record_seconds:', cfg.get('record_seconds'))
print('[BX1] auto_camera_on_vision_request:', cfg.get('auto_camera_on_vision_request'))
print('[BX1] brain_base_url:', cfg.get('brain_base_url'))
print('[BX1] brain_tts_base_url:', cfg.get('brain_tts_base_url'))
PY
sudo systemctl restart bx1-web.service
sleep 8
systemctl status bx1-web.service --no-pager -l || true
ss -ltnp | grep 8088 || true
