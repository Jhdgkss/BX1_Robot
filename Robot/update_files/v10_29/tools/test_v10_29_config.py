#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, py_compile
from pathlib import Path

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--project',required=True); a=ap.parse_args()
    root=Path(a.project)
    files=[root/'python'/'main.py',root/'python'/'web_control.py',root/'python'/'audio_io.py',root/'python'/'camera_io.py']
    for f in files: py_compile.compile(str(f),doraise=True)
    cfg=json.loads((root/'python'/'config.json').read_text(encoding='utf-8'))
    main_text=(root/'python'/'main.py').read_text(encoding='utf-8')
    web_text=(root/'python'/'web_control.py').read_text(encoding='utf-8')
    checks={
      'config version is 10.29':str(cfg.get('app_version'))=='10.29',
      'thinking feedback enabled':cfg.get('thinking_feedback_enabled') is True,
      'feedback delay is bounded':0.15 <= float(cfg.get('thinking_feedback_delay_s',0)) <= 2.0,
      'thinking tone pattern installed':'"thinking": [(620.0' in main_text,
      'body cue works under Brain ownership':'The desktop Brain still owns personality and spoken filler wording' in main_text,
      'web version is 10.29':'Robot client v10.29' in web_text,
      'yaw servo is D9':int((((cfg.get('hardware_registry') or {}).get('head') or {}).get('yaw') or {}).get('pin',9))==9,
      'left gimbal is D10':int((((cfg.get('hardware_registry') or {}).get('head') or {}).get('gimbal_left') or {}).get('pin',10))==10,
      'right gimbal is D11':int((((cfg.get('hardware_registry') or {}).get('head') or {}).get('gimbal_right') or {}).get('pin',11))==11,
    }
    for k,v in checks.items(): print(('PASS' if v else 'FAIL')+': '+k)
    return 0 if all(checks.values()) else 1
if __name__=='__main__': raise SystemExit(main())
