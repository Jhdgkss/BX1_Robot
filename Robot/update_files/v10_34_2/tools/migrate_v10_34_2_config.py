#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print('Usage: migrate_v10_34_2_config.py /path/to/python/config.json', file=sys.stderr)
        return 2
    path = Path(sys.argv[1]).expanduser().resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit('config root must be a JSON object')

    data['app_version'] = '10.34.2'
    data['version'] = '10.34.2'

    # Keep the deliberately natural one-word wake entries.
    data['wake_words'] = ['hello', 'hey', 'robot']

    # A spoken "Yes John?" occupied the microphone for around 3-4 seconds and
    # caused the question immediately after Hey to be lost. Keep the fast chirp
    # and visual acknowledgement, but open the mic again immediately.
    data['wake_voice_ack_enabled'] = False
    data['wake_command_window_s'] = 20.0
    data['conversation_followup_window_s'] = 90.0
    data['wake_after_reply_guard_s'] = 0.8
    data['stt_post_tts_guard_s'] = 0.8

    # The trace shows a strong microphone signal. Improve short-phrase pickup
    # without relaxing the noise gate enough to reintroduce room-noise commands.
    data['stt_start_trigger_ms'] = 80
    data['stt_min_voiced_ms'] = 240
    data['stt_min_longest_voiced_ms'] = 120
    data['stt_end_silence_ms'] = 850
    data['stt_start_timeout_s'] = 10.0

    # The robot body owns immediate progress feedback because it knows when the
    # physical Chatterbox audio is actually ready. One heard chirp, then a cached
    # personality phrase if the response remains pending.
    data['brain_controls_thinking_cues'] = False
    data['voice_command_immediate_cue_enabled'] = True
    data['voice_feedback_audio_enabled'] = True
    data['voice_feedback_led_enabled'] = True
    data['voice_feedback_tone_level'] = 0.30
    data['thinking_feedback_enabled'] = False  # avoid a second chirp after heard
    data['thinking_cues_enabled'] = True
    data['thinking_cue_speak'] = True
    data['thinking_cue_delay_s'] = 1.0
    data['thinking_cue_repeat_s'] = 10.0
    data['thinking_cue_max_per_reply'] = 2
    data['thinking_cue_total_timeout_s'] = 45.0
    data['thinking_cue_finish_wait_s'] = 1.0
    data['thinking_cues_continue_through_tts_generation'] = True
    data['thinking_cue_use_main_tts_when_uncached'] = False
    data['local_voice_cue_cache_enabled'] = True
    data['local_cue_fallback_espeak_enabled'] = True
    data['thinking_cues'] = [
        'Let me think.',
        'One moment.',
        'I am checking that.',
        'Hmm.',
    ]

    # Keep replies short enough for Chatterbox. Serial sentence chunking can add
    # long pauses between chunks, so avoid splitting normal conversational replies.
    data['tts_chunking_enabled'] = True
    data['tts_chunk_max_chars'] = 220

    # Restore bounded idle-life phases.
    data['idle_life_enabled'] = True
    data['idle_life_micro_actions_enabled'] = True
    data['idle_life_self_chatter_enabled'] = True
    data.setdefault('idle_life_response_mode', 'brain')

    # The trace confirms this is the correct, healthy input and should never be
    # replaced by ALSA "default" during migration.
    data['mic_device'] = 'plughw:0,0'
    data['stt_capture_method'] = 'alsa'
    data['sample_rate'] = 16000
    data['mic_channels'] = 1

    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Migrated {path} to BX1 body v10.34.2')
    print('Microphone:', data['mic_device'])
    print('Wake acknowledgement: fast chirp only')
    print('Follow-up window: starts after physical speech playback')
    print('Local thinking phrases: enabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
