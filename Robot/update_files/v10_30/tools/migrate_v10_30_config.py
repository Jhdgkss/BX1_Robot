#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime
from pathlib import Path
PRESERVE_KEYS={'brain_base_url','brain_api_key','mic_device','tts_playback_device','vosk_model_path','hardware_registry','hardware_map','servo_trims','wake_words','led_state_profiles'}
ADDITIONS={
 'app_version':'10.30','version':'10.30',
 'brain_controls_thinking_cues':False,
 'thinking_cues_enabled':True,'thinking_cue_speak':True,
 'thinking_feedback_enabled':True,'thinking_feedback_delay_s':0.35,
 'thinking_feedback_max_per_reply':1,
 'thinking_cue_delay_s':1.15,'thinking_cue_repeat_s':5.5,'thinking_cue_max_per_reply':2,
 'thinking_cue_use_main_tts_when_uncached':False,
 'voice_command_immediate_cue_enabled':False,
 'local_cue_fallback_espeak_enabled':True,
 'thinking_cues':['Hmm.','Let me check that.','One moment.','I am looking into it.','Still working on that.'],
}
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('config'); ap.add_argument('--defaults',required=True); a=ap.parse_args()
 path=Path(a.config); defaults=Path(a.defaults)
 if not path.exists(): raise SystemExit(f'Missing config: {path}')
 current=json.loads(path.read_text(encoding='utf-8')); base=json.loads(defaults.read_text(encoding='utf-8'))
 stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); backup=path.with_name(path.name+f'.before_v10_30_{stamp}'); shutil.copy2(path,backup)
 merged=dict(base); merged.update(current); merged.update(ADDITIONS)
 for key in PRESERVE_KEYS:
  if key in current: merged[key]=current[key]
 path.write_text(json.dumps(merged,indent=4,ensure_ascii=False)+'\n',encoding='utf-8')
 print(f'Migrated {path} to BX1 v10.30'); print(f'Backup: {backup}')
 print('Thinking phases: chirp, then short spoken progress phrase while Brain is still working')
if __name__=='__main__': main()
