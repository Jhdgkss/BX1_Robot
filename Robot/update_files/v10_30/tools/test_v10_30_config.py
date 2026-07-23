#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,py_compile,re
from pathlib import Path
def need(c,m):
 if not c: raise AssertionError(m)
 print('PASS:',m)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--project',required=True); a=ap.parse_args(); root=Path(a.project)
 for f in ('python/main.py','python/web_control.py','python/config.json'):
  need((root/f).exists(),f'exists: {f}')
 py_compile.compile(str(root/'python/main.py'),doraise=True); py_compile.compile(str(root/'python/web_control.py'),doraise=True)
 cfg=json.loads((root/'python/config.json').read_text())
 need(str(cfg.get('version'))=='10.30','config version 10.30')
 need(bool(cfg.get('thinking_cues_enabled')),'spoken thinking phases enabled')
 need(bool(cfg.get('thinking_cue_speak')),'thinking speech enabled')
 need(not bool(cfg.get('brain_controls_thinking_cues')),'body may render bounded progress phrases')
 text=(root/'python/web_control.py').read_text()
 need('conversationHeard' in text,'robot web displays what BX1 heard')
 need('thinking_phase' in (root/'python/main.py').read_text(),'thinking phase runtime installed')
 print('VALIDATION PASSED: Body v10.30')
if __name__=='__main__': main()
