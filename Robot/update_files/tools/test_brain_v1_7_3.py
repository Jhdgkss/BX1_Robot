#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, py_compile
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--project',required=True); a=ap.parse_args()
    root=Path(a.project)
    main_py=root/'main_pyqt.py'; cfg=root/'config'/'app_config_bx1.json'
    py_compile.compile(str(main_py),doraise=True)
    text=main_py.read_text(encoding='utf-8')
    checks={
      'fast voice helper':'def _is_fast_voice_request' in text,
      'compact prompt':'FAST SPOKEN CONVERSATION MODE' in text,
      'ollama keep alive':'ollama_keep_alive' in text,
      'short voice token cap':'fast_voice_num_predict' in text,
      'personality repair skipped in fast route':'reply if fast_voice_mode else self.repair_reply_personality' in text,
    }
    if cfg.exists():
      d=json.loads(cfg.read_text(encoding='utf-8'))
      checks.update({
        'config version 1.7.3':str(d.get('app_version','')).startswith('Robot Brain V1.7.3'),
        'fast voice enabled':d.get('fast_voice_mode_enabled') is True,
        'current model preserved':bool(d.get('model')),
      })
    bad=[k for k,v in checks.items() if not v]
    for k,v in checks.items(): print(('PASS' if v else 'FAIL')+': '+k)
    return 1 if bad else 0
if __name__=='__main__': raise SystemExit(main())
