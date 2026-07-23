#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime
from pathlib import Path

PRESERVE_KEYS = {
    'brain_base_url','brain_api_key','mic_device','tts_playback_device','vosk_model_path',
    'hardware_registry','hardware_map','servo_trims','wake_words','led_state_profiles',
}

ADDITIONS = {
    'app_version':'10.29',
    'version':'10.29',
    'thinking_feedback_enabled':True,
    'thinking_feedback_delay_s':0.45,
    'thinking_feedback_repeat_s':4.0,
    'thinking_feedback_max_per_reply':2,
    'brain_controls_thinking_cues':True,
}

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('config')
    ap.add_argument('--defaults',required=True)
    a=ap.parse_args()
    path=Path(a.config); defaults_path=Path(a.defaults)
    if not path.exists(): raise SystemExit(f'Missing config: {path}')
    current=json.loads(path.read_text(encoding='utf-8'))
    defaults=json.loads(defaults_path.read_text(encoding='utf-8'))
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=path.with_name(path.name+f'.before_v10_29_{stamp}')
    shutil.copy2(path,backup)
    merged=dict(defaults)
    merged.update(current)
    merged.update(ADDITIONS)
    # Current values win for all hardware and connection settings.
    for k in PRESERVE_KEYS:
        if k in current: merged[k]=current[k]
    path.write_text(json.dumps(merged,indent=4,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Migrated {path} to BX1 v10.29')
    print(f'Backup: {backup}')
    print('Thinking feedback: immediate body-side tone + thinking LED while Brain is working')
    return 0
if __name__=='__main__': raise SystemExit(main())
