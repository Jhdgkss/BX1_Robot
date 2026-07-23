#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: test_v10_34_2.py /path/to/project', file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    for rel in ('python/main.py', 'python/audio_io.py', 'python/web_control.py', 'python/camera_io.py'):
        path = root / rel
        require(path.exists(), f'missing {rel}')
        ast.parse(path.read_text(encoding='utf-8'))

    main_text = (root / 'python/main.py').read_text(encoding='utf-8')
    camera_text = (root / 'python/camera_io.py').read_text(encoding='utf-8')
    web_text = (root / 'python/web_control.py').read_text(encoding='utf-8')
    require('Reply finished. Listening for follow-up' in main_text, 'post-playback follow-up reset missing')
    require('CAP_V4L2' in camera_text, 'V4L2 camera backend fix missing')
    require('dirty' in web_text.lower(), 'microphone selection refresh protection missing')

    cfg = json.loads((root / 'python/config.json').read_text(encoding='utf-8'))
    require(cfg.get('app_version') == '10.34.2', 'config version mismatch')
    require(cfg.get('mic_device') == 'plughw:0,0', 'microphone changed')
    require(cfg.get('wake_words') == ['hello', 'hey', 'robot'], 'wake words changed')
    require(cfg.get('wake_voice_ack_enabled') is False, 'blocking spoken wake acknowledgement still enabled')
    require(cfg.get('thinking_cues_enabled') is True, 'thinking cues not enabled')
    require(cfg.get('voice_command_immediate_cue_enabled') is True, 'heard acknowledgement not enabled')
    require(float(cfg.get('conversation_followup_window_s', 0)) >= 90, 'follow-up window too short')
    print('PASS: BX1 body v10.34.2 response and listening self-test')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
