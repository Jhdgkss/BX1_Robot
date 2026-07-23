#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from datetime import datetime
from pathlib import Path

DEFAULTS = {
    "app_version": "Robot Brain V1.7.3 - Fast Voice + Thinking Feedback",
    "ollama_keep_alive": "30m",
    "fast_voice_mode_enabled": True,
    "fast_voice_max_input_chars": 220,
    "fast_voice_num_predict": 160,
    "fast_voice_history_messages": 4,
    "fast_voice_reply_word_target": 45,
    "processing_filler_enabled": True,
}

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('config')
    args=ap.parse_args()
    path=Path(args.config)
    if not path.exists():
        print(f'SKIP: {path} does not exist')
        return 0
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    backup=path.with_name(path.name+f'.before_v1_7_3_{stamp}')
    shutil.copy2(path,backup)
    data=json.loads(path.read_text(encoding='utf-8'))
    for k,v in DEFAULTS.items():
        if k=='app_version' or k not in data:
            data[k]=v
    # Keep the current model and all voice/personality/profile settings.
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f'Migrated {path}')
    print(f'Backup: {backup}')
    return 0
if __name__=='__main__': raise SystemExit(main())
