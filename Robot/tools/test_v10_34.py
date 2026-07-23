#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f'missing {label}: {needle}')


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: test_v10_34.py /path/to/project', file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).expanduser().resolve()
    files = {
        'main': root / 'python' / 'main.py',
        'audio': root / 'python' / 'audio_io.py',
        'web': root / 'python' / 'web_control.py',
        'doctor': root / 'python' / 'hardware_doctor.py',
        'sketch': root / 'sketch' / 'sketch.ino',
        'config': root / 'python' / 'config.json',
    }
    for label, path in files.items():
        if not path.is_file():
            raise AssertionError(f'missing {label}: {path}')

    for label in ('main', 'audio', 'web', 'doctor'):
        ast.parse(files[label].read_text(encoding='utf-8'), filename=str(files[label]))

    main_text = files['main'].read_text(encoding='utf-8')
    require(main_text, 'Building the Chatterbox voice; progress cues remain active.', 'generation state')
    require(main_text, 'reply_audio_ready', 'cue stop at physical playback')
    require(main_text, 'self.local_cue_playing', 'local cue overlap gate')
    require(main_text, '"owner": "robot_body_runtime"', 'body cue ownership')
    require(main_text, 'thinking_cue_total_timeout_s', 'bounded cue lifetime')
    require(main_text, 'tts_continuation', 'feedback between generated speech chunks')
    require(main_text, 'if bool(self.cfg.get("voice_command_immediate_cue_enabled", True))', 'immediate heard acknowledgement')

    audio_text = files['audio'].read_text(encoding='utf-8')
    require(audio_text, '[audio] Brain TTS ready:', 'TTS generation timing log')
    require(audio_text, '[audio] Reply playback starting:', 'physical playback timing log')
    require(audio_text, 'total_generation_download_s', 'TTS timing metric')

    cfg = json.loads(files['config'].read_text(encoding='utf-8'))
    assert str(cfg.get('app_version')) == '10.34'
    assert cfg.get('brain_controls_thinking_cues') is False
    assert cfg.get('thinking_cues_enabled') is True
    assert cfg.get('thinking_cue_speak') is True
    assert cfg.get('voice_command_immediate_cue_enabled') is True
    assert float(cfg.get('thinking_cue_delay_s', 99)) <= 1.2
    assert int(cfg.get('thinking_cue_max_per_reply', 0)) >= 3
    assert cfg.get('tts_chunking_enabled') is True
    assert int(cfg.get('tts_chunk_max_chars', 999)) <= 180
    assert cfg.get('idle_life_enabled') is True
    assert cfg.get('idle_life_micro_actions_enabled') is True
    assert cfg.get('idle_life_self_chatter_enabled') is True
    assert [str(x).lower() for x in cfg.get('wake_words', [])] == ['hello', 'hey', 'robot']
    assert str(cfg.get('mic_device') or '').strip()

    print('BX1 v10.34 response-feedback self-test: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
