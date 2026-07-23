#!/usr/bin/env python3
import argparse, json, py_compile
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--project',required=True); a=ap.parse_args(); root=Path(a.project)
for rel in ['python/main.py','python/web_control.py','python/audio_io.py','python/bx1_robot_client.py']:
    py_compile.compile(str(root/rel),doraise=True)
cfg=json.loads((root/'python/config.json').read_text(encoding='utf-8'))
assert cfg['app_version']=='10.32'; assert cfg['brain_controls_thinking_cues'] is False
assert cfg['thinking_feedback_enabled'] and cfg['thinking_cues_enabled']; assert cfg['stt_pre_roll_ms']>=800
print('BX1 body v10.32 validation passed')
