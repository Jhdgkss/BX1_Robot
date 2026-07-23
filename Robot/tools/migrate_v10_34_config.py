#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: migrate_v10_34_config.py /path/to/python/config.json', file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).expanduser().resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit('config root must be a JSON object')

    data['app_version'] = '10.34'
    data['version'] = '10.34'

    # Keep the natural one-word wake entries explicitly requested by the user.
    data.setdefault('wake_words', ['hello', 'hey', 'robot'])

    # The Brain owns personality and answer wording; the body owns immediate,
    # locally playable acknowledgement/progress cues and knows when physical
    # playback really begins.
    data['brain_controls_thinking_cues'] = False
    data['thinking_feedback_enabled'] = True
    data['thinking_feedback_delay_s'] = 0.18
    data['voice_command_immediate_cue_enabled'] = True
    data['voice_feedback_audio_enabled'] = True
    data['voice_feedback_led_enabled'] = True
    data['voice_feedback_tone_level'] = 0.30
    data['thinking_cues_enabled'] = True
    data['thinking_cue_speak'] = True
    data['thinking_cue_delay_s'] = 1.10
    data['thinking_cue_repeat_s'] = 8.0
    data['thinking_cue_max_per_reply'] = 5
    data['thinking_cue_total_timeout_s'] = 65.0
    data['thinking_cue_finish_wait_s'] = 2.2
    data['thinking_cues_continue_through_tts_generation'] = True
    data['thinking_cue_use_main_tts_when_uncached'] = False
    data['thinking_cues'] = [
        'Let me think.',
        'One moment.',
        'I am checking that.',
        'Hmm.',
        'Processing.',
    ]

    # Generate longer answers in smaller sentence groups. This does not make the
    # Chatterbox model itself faster, but it lets the first useful speech start
    # before the whole multi-sentence response has been rendered.
    data['tts_chunking_enabled'] = True
    data['tts_chunk_max_chars'] = 180

    # Restore the existing idle-life phases. These remain bounded by the
    # existing idle timers and per-hour limits.
    data['idle_life_enabled'] = True
    data['idle_life_micro_actions_enabled'] = True
    data['idle_life_self_chatter_enabled'] = True

    # Preserve known-good device selections such as plughw:0,0. Only fill a
    # missing microphone field; never overwrite a working explicit device.
    if not str(data.get('mic_device') or '').strip():
        data['mic_device'] = 'plughw:0,0'

    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Migrated {path} to BX1 body v10.34')
    print('Local acknowledgement/progress cues: enabled')
    print('Idle-life micro-actions and bounded self-chatter: enabled')
    print('Microphone device preserved as:', data.get('mic_device'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
