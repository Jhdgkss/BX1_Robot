#!/usr/bin/env python3
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('config'); ap.add_argument('--defaults',required=True); a=ap.parse_args()
    p=Path(a.config); d=Path(a.defaults); cfg=json.loads(p.read_text(encoding='utf-8')); defaults=json.loads(d.read_text(encoding='utf-8'))
    preserve={'brain_base_url','brain_tts_base_url','mic_device','tts_playback_device','tts_voice','brain_tts_voice','robot_id','robot_name','wake_words'}
    forced={
      'app_version':'10.32','version':'10.32','stt_pre_roll_ms':850,'stt_end_silence_ms':1400,'stt_post_roll_ms':320,
      'stt_start_trigger_ms':60,'stt_adaptive_margin_db':4.5,'stt_min_confidence':0.35,
      'wake_fuzzy_matching_enabled':True,'wake_fuzzy_threshold':0.74,'wake_match_first_tokens':4,
      'thinking_feedback_enabled':True,'thinking_feedback_delay_s':0.65,'thinking_cues_enabled':True,
      'thinking_cue_speak':True,'thinking_cue_delay_s':2.1,'thinking_cue_repeat_s':5.0,
      'thinking_cue_max_per_reply':2,'brain_controls_thinking_cues':False,'brain_request_watchdog_s':50.0,
    }
    for k,v in defaults.items():
        if k not in cfg: cfg[k]=v
    cfg.update(forced)
    if not isinstance(cfg.get('wake_word_aliases'),dict): cfg['wake_word_aliases']=defaults.get('wake_word_aliases',{})
    p.write_text(json.dumps(cfg,indent=4,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Migrated',p,'to',cfg.get('app_version'))
if __name__=='__main__': main()
